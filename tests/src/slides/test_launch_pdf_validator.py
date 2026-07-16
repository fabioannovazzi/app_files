from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from modules.utilities.config import get_naming_params
from src.slides import launch_pdf_validator as validator
from src.slides.models import Deck, Slide


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if rows:
        pl.DataFrame(rows).write_csv(path)
        return
    pl.DataFrame().write_csv(path)


def _make_launch_package(
    root: Path,
    *,
    category_key: str,
    category_label: str,
    retailer: str = "ulta",
) -> Path:
    package_dir = root / category_key
    package_dir.mkdir(parents=True)
    (package_dir / "pack_manifest.json").write_text(
        (
            "{\n"
            f'  "retailer": "{retailer}",\n'
            f'  "category_key": "{category_key}",\n'
            f'  "category_label": "{category_label}"\n'
            "}\n"
        ),
        encoding="utf-8",
    )
    (package_dir / "summary.json").write_text(
        (
            "{\n"
            f'  "retailer": "{retailer}",\n'
            f'  "category_label": "{category_label}"\n'
            "}\n"
        ),
        encoding="utf-8",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "pink + stick",
                "count_recent": 21,
                "count_rest": 76,
                "pct_recent": 0.467,
                "pct_rest": 0.432,
                "recent_brand_count": 7,
            },
            {
                "bundle_label": "red + stick",
                "count_recent": 18,
                "count_rest": 69,
                "pct_recent": 0.400,
                "pct_rest": 0.390,
                "recent_brand_count": 6,
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "stick + stick",
                "count_top_seller": 26,
                "count_other": 91,
                "pct_top_seller": 0.578,
                "pct_other": 0.551,
                "top_seller_brand_count": 8,
            }
        ],
    )
    _write_csv(package_dir / "top_seller_triples.csv", [])
    _write_csv(package_dir / "innovation_triples.csv", [])
    _write_csv(package_dir / "filter_comparison.csv", [])
    _write_csv(package_dir / "mapped_attribute_comparison.csv", [])
    _write_csv(package_dir / "resolved_core_comparison.csv", [])
    _write_csv(package_dir / "top_seller_mapped_attribute_comparison.csv", [])
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "BRAND ALPHA",
                "catalog_share": 0.08,
                "top_seller_share_of_cohort": 0.11,
                "over_index_vs_catalog_share": 1.38,
            }
        ],
    )
    _write_csv(
        package_dir / "recent_products.csv",
        [
            {
                "product_name": "Hero Product",
                "brand": "BRAND ALPHA",
                "pareto_rank": 11,
                "pareto_bucket": "A",
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Hero Product",
                "brand": "BRAND ALPHA",
                "pareto_rank": 11,
                "pareto_bucket": "A",
            }
        ],
    )
    return package_dir


def _fake_reading_payload() -> dict[str, object]:
    return {
        "deck_id": "lipstick",
        "lang": "eng",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": "table-1",
                        "type": "table",
                        "table_model": {
                            "header_rows": 1,
                            "rows": [
                                {
                                    "cells": [
                                        {"text": "Attribute"},
                                        {"text": "Recent (%)"},
                                        {"text": "Rest (%)"},
                                    ]
                                },
                                {
                                    "cells": [
                                        {"text": "Pink + stick form"},
                                        {"text": "46.7%"},
                                        {"text": "43.2%"},
                                    ]
                                },
                                {
                                    "cells": [
                                        {"text": "Red + stick form"},
                                        {"text": "40.0%"},
                                        {"text": "39.0%"},
                                    ]
                                },
                            ],
                        },
                    },
                    {
                        "block_id": "brand-1",
                        "type": "text",
                        "text": "BRAND ALPHA is 11.0% of the top-seller cohort from 8.0% of catalog share (1.38x over-index).",
                    },
                    {
                        "block_id": "product-1",
                        "type": "text",
                        "text": "Hero Product (#11 Pareto A)",
                    },
                    {
                        "block_id": "chart-1",
                        "type": "chart",
                        "visual_text": "The pink + stick chart highlights the 46.7% recent share.",
                        "visual_items": [
                            "Pink + stick form recent share 46.7%",
                        ],
                    },
                    {
                        "block_id": "narrative-1",
                        "type": "text",
                        "text": "The category is anchored by broad beige/pink/red shade ranges.",
                    },
                ],
                "figure_regions": [{"x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0}],
            }
        ],
    }


def _fake_cached_analysis_payload() -> dict[str, object]:
    return {
        "deckId": "lipstick",
        "lang": "eng",
        "slides": [
            {
                "slideId": "slide-1",
                "slideNumber": 1,
                "pageNumber": 1,
                "blocks": [
                    {
                        "blockId": "block-1",
                        "type": "text",
                        "text": "Cached title block",
                        "items": [],
                        "confidence": 0.91,
                        "auditStatus": "ok",
                        "visualStatus": "corrected",
                        "visualConfidence": 0.94,
                    }
                ],
                "titleText": "Cached title",
                "bulletTexts": [],
                "figureRegions": [],
            }
        ],
    }


def test_resolve_launch_package_for_pdf_handles_alias_and_missing_match(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "packages" / "launch"
    expected_balms = _make_launch_package(
        package_root / "ulta",
        category_key="lip_balm",
        category_label="lip balm",
    )
    expected_permanent = _make_launch_package(
        package_root / "saloncentric",
        category_key="permanent",
        category_label="permanent haircolor",
        retailer="saloncentric",
    )
    expected_creams = _make_launch_package(
        package_root / "ulta",
        category_key="bb_cc_creams",
        category_label="bb cc creams",
    )
    expected_setting = _make_launch_package(
        package_root / "ulta",
        category_key="setting_spray_powder",
        category_label="setting spray & powder",
    )
    expected_cashmere = _make_launch_package(
        package_root / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    expected_sneakers = _make_launch_package(
        package_root / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low-top sneakers",
        retailer="saksfifthavenue",
    )

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/lip_balm.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is not None
    assert resolved.package_dir == expected_balms
    assert details["status"] == "matched"

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/permanent_saloncentric.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is not None
    assert resolved.package_dir == expected_permanent
    assert details["status"] == "matched"

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/lip_balm_ulta.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is not None
    assert resolved.package_dir == expected_balms
    assert details["retailer_hint"] == "ulta"

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/cream_ulta.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is not None
    assert resolved.package_dir == expected_creams
    assert details["normalized_key"] == "bb_cc_creams"

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/setting_spray_and_powder_ulta.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is not None
    assert resolved.package_dir == expected_setting
    assert details["normalized_key"] == "setting_spray_powder"

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/cashmere_sweaters.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is not None
    assert resolved.package_dir == expected_cashmere
    assert details["retailer_hint"] is None

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/sneaker_saks.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is not None
    assert resolved.package_dir == expected_sneakers
    assert details["normalized_key"] == "low_top_sneakers"

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/permanent_cosmoprof.pdf"),
        package_roots=(package_root,),
    )
    assert resolved is None
    assert details["status"] == "unresolved"


def test_resolve_launch_package_for_pdf_discovers_package_without_manifest(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "packages" / "launch"
    package_dir = package_root / "ulta" / "blush"
    package_dir.mkdir(parents=True)
    (package_dir / "summary.json").write_text(
        '{"retailer": "ulta", "category_label": "blush"}',
        encoding="utf-8",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "pink + liquid",
                "count_recent": 3,
                "count_rest": 5,
                "pct_recent": 0.3,
                "pct_rest": 0.2,
            }
        ],
    )

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/blush_ulta.pdf"),
        package_roots=(package_root,),
    )

    assert resolved is not None
    assert resolved.package_dir == package_dir
    assert resolved.retailer == "ulta"
    assert resolved.category_key == "blush"
    assert details["status"] == "matched"


def test_resolve_launch_package_for_pdf_reports_package_discovery_diagnostics(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "packages" / "launch"

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/blush_ulta.pdf"),
        package_roots=(missing_root,),
    )

    assert resolved is None
    assert details["status"] == "unresolved"
    assert details["reason"] == "no_matching_package"
    assert details["discovered_package_count"] == 0
    assert details["package_roots"] == [
        {"path": str(missing_root.resolve()), "exists": False}
    ]


def test_resolve_launch_package_for_pdf_allows_unknown_retailer_when_category_matches(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "packages" / "launch"
    package_dir = package_root / "blush"
    package_dir.mkdir(parents=True)
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "pink + liquid",
                "count_recent": 3,
                "count_rest": 5,
                "pct_recent": 0.3,
                "pct_rest": 0.2,
            }
        ],
    )

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/blush_ulta.pdf"),
        package_roots=(package_root,),
    )

    assert resolved is not None
    assert resolved.package_dir == package_dir
    assert resolved.retailer == ""
    assert details["status"] == "matched"


def test_resolve_launch_package_for_pdf_lists_discovered_packages_on_missing_match(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "packages" / "launch"
    package_dir = package_root / "ulta" / "blush"
    package_dir.mkdir(parents=True)
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "pink + liquid",
                "count_recent": 3,
                "count_rest": 5,
                "pct_recent": 0.3,
                "pct_rest": 0.2,
            }
        ],
    )

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/bronzer_ulta.pdf"),
        package_roots=(package_root,),
    )

    assert resolved is None
    assert details["discovered_package_count"] == 1
    assert details["discovered_packages"] == [
        {
            "path": str(package_dir.resolve()),
            "retailer": "ulta",
            "category_key": "blush",
            "category_label": "blush",
        }
    ]


def test_resolve_launch_package_for_pdf_strips_retailer_suffix_from_package_names(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "packages" / "launch"
    package_dir = package_root / "blush_ulta"
    package_dir.mkdir(parents=True)
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "pink + liquid",
                "count_recent": 3,
                "count_rest": 5,
                "pct_recent": 0.3,
                "pct_rest": 0.2,
            }
        ],
    )

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/blush_ulta.pdf"),
        package_roots=(package_root,),
    )

    assert resolved is not None
    assert resolved.package_dir == package_dir
    assert details["status"] == "matched"


def test_resolve_launch_package_for_pdf_handles_category_without_retailer_suffix(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "packages" / "launch"
    package_dir = package_root / "wet_cat_food" / "chewy"
    package_dir.mkdir(parents=True)
    (package_dir / "pack_manifest.json").write_text(
        json.dumps(
            {
                "retailer": "chewy",
                "category_key": "wet_cat_food",
                "category_label": "wet cat food",
            }
        ),
        encoding="utf-8",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "pate + chicken",
                "count_recent": 3,
                "count_rest": 5,
                "pct_recent": 0.3,
                "pct_rest": 0.2,
            }
        ],
    )

    resolved, details = validator.resolve_launch_package_for_pdf(
        Path("launch_reports/wet_cat_food.pdf"),
        package_roots=(package_root,),
    )

    assert resolved is not None
    assert resolved.package_dir == package_dir
    assert details["status"] == "matched"
    assert details["normalized_key"] == "wet_cat_food"
    assert details["retailer_hint"] is None


def test_validate_launch_report_pdf_marks_verified_and_unresolved_items(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: _fake_reading_payload(),
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["verified_count"] == 4
    assert payload["summary"]["contradicted_count"] == 0
    assert payload["summary"]["unresolved_count"] == 0
    assert payload["summary"]["partially_backed_count"] == 1
    assert payload["summary"]["image_region_count"] == 1
    assert payload["reading_quality"]["status"] == "read_ok"
    fingerprint = payload["package"]["content_fingerprint"]
    assert len(fingerprint["content_sha256"]) == 64
    assert fingerprint["file_count"] >= 2
    assert any(item["file"] == "top_seller_pairs.csv" for item in fingerprint["files"])
    assert payload["generation_source"]["status"] == "not_found"
    families = {item["claim_family"] for item in payload["claims"]}
    assert families == {
        "brand_share",
        "bundle_metric",
        "product_rank",
        "summary_synthesis",
    }
    assert all(item["source_kind"] != "visual_item" for item in payload["claims"])
    bundle_claim = next(
        item for item in payload["claims"] if item["claim_family"] == "bundle_metric"
    )
    assert bundle_claim["details"]["source_file"] in {
        "innovation_pairs.csv",
        "top_seller_pairs.csv",
    }
    assert "observed_values" in bundle_claim["details"]
    assert "package_values" in bundle_claim["details"]
    brand_claim = next(
        item for item in payload["claims"] if item["claim_family"] == "brand_share"
    )
    assert brand_claim["details"]["brand_name"] == "BRAND ALPHA"
    assert brand_claim["details"]["source_file"] == "top_seller_brand_comparison.csv"
    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert payload["image_regions"][0]["claim_family"] == "figure_region"


def test_validate_launch_report_pdf_checks_rank_only_product_rank_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(package_dir / "recent_products.csv", [])
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": (
                    "Pet Brand Alpha Gravy Variety Pack "
                    "Canned Cat Food, 3-oz, case of 24"
                ),
                "brand": "Pet Brand Alpha",
                "pareto_rank": 1,
                "pareto_bucket": "A",
            },
            {
                "product_name": (
                    "Pet Brand Alpha Classic Seafood Variety Pack Canned Cat "
                    "Food, 3-oz, case of 24"
                ),
                "brand": "Pet Brand Alpha",
                "pareto_rank": 3,
                "pareto_bucket": "A",
            },
            {
                "product_name": (
                    "Pet Brand Gamma Portion Trays with Chicken, Salmon & "
                    "Tender Turkey Cuts in Gravy Variety Pack"
                ),
                "brand": "Pet Brand Gamma",
                "pareto_rank": 14,
                "pareto_bucket": "A",
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "blocks": [
                        {
                            "block_id": "rank-1",
                            "type": "text",
                            "text": (
                                "The number one top-selling product overall is "
                                "Pet Brand Alpha Gravy Variety Pack "
                                "Variety Pack."
                            ),
                        },
                        {
                            "block_id": "rank-3",
                            "type": "text",
                            "text": (
                                "Top-seller data confirms this format's dominance, "
                                "exemplified by Pet Brand Alpha Classic Seafood "
                                "(#3 overall rank)."
                            ),
                        },
                        {
                            "block_id": "rank-14",
                            "type": "text",
                            "text": (
                                "Pet Brand Gamma Portion Trays (#14 rank) is the strongest "
                                "embodiment of this format."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    product_rank_claims = [
        item for item in payload["claims"] if item["claim_family"] == "product_rank"
    ]
    assert payload["summary"]["unresolved_count"] == 0
    assert len(product_rank_claims) == 3
    assert {
        claim["details"]["observed_values"]["claimed_rank"]
        for claim in product_rank_claims
    } == {
        1,
        3,
        14,
    }
    assert all(
        claim["status"] == "verified"
        and claim["details"]["observed_values"]["claimed_bucket"] is None
        for claim in product_rank_claims
    )


def test_validate_launch_report_pdf_checks_ranked_bundle_product_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(package_dir / "recent_products.csv", [])
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Pet Brand Alpha Gravy Variety Pack",
                "brand": "Pet Brand Alpha",
                "pareto_rank": 1,
                "pareto_bucket": "A",
                "food texture": "Chunks in Gravy",
                "packaging type": "Can",
            },
            {
                "product_name": "Pet Brand Alpha Classic Seafood Variety Pack",
                "brand": "Pet Brand Alpha",
                "pareto_rank": 3,
                "pareto_bucket": "A",
                "food texture": "Pate",
                "packaging type": "Can",
            },
            {
                "product_name": "Pet Brand Beta Seafood and Chicken Pate",
                "brand": "Pet Brand Beta",
                "pareto_rank": 5,
                "pareto_bucket": "A",
                "food texture": "Pate",
                "packaging type": "Can",
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "blocks": [
                        {
                            "block_id": "bundle-rank-1",
                            "type": "text",
                            "text": (
                                "Pate in Can: Signal Read Dominant Shelf Signal; "
                                "Visibility Metric Top-ranked products "
                                "(#3, #5 sellers)"
                            ),
                        },
                        {
                            "block_id": "bundle-rank-2",
                            "type": "text",
                            "text": (
                                "Chunks in Gravy in Can: Signal Read Dominant "
                                "Shelf Signal; Visibility Metric Top-ranked "
                                "product (#1 seller)"
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claims = [
        item
        for item in payload["claims"]
        if item["claim_family"] == "ranked_bundle_product_evidence"
    ]
    assert payload["summary"]["unresolved_count"] == 0
    assert len(claims) == 2
    assert {
        tuple(claim["details"]["observed_values"]["claimed_ranks"]) for claim in claims
    } == {
        (1,),
        (3, 5),
    }
    assert all(claim["status"] == "verified" for claim in claims)


def test_validate_launch_report_pdf_checks_wet_food_review_texture_and_packaging_friction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "bundle_review_validation.csv",
        [
            {
                "bundle_label": "Pate + Can",
                "product_name": "Pet Brand Alpha Classic Seafood Pate",
                "reviews_positive_headline": "Smooth texture",
                "reviews_positive_comment": "Soft pate texture that cats prefer.",
                "reviews_negative_headline": "",
                "reviews_negative_comment": "",
            },
            {
                "bundle_label": "Pate + Can",
                "product_name": "Pet Brand Beta Seafood Pate",
                "reviews_positive_headline": "Soft pate",
                "reviews_positive_comment": "Smooth food texture and easy eating.",
                "reviews_negative_headline": "",
                "reviews_negative_comment": "",
            },
            {
                "bundle_label": "Prescription + Health",
                "product_name": "Therapeutic Chunks in Gravy",
                "reviews_positive_headline": "Smooth texture",
                "reviews_positive_comment": "Soft texture that cats prefer.",
                "reviews_negative_headline": "",
                "reviews_negative_comment": "",
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_review_validation.csv",
        [
            {
                "bundle_label": "Tray + Chunks in Gravy",
                "product_name": "Pet Brand Gamma Portion Trays",
                "reviews_positive_headline": "",
                "reviews_positive_comment": "",
                "reviews_negative_headline": "Hard to open",
                "reviews_negative_comment": (
                    "The package seal is difficult to open cleanly."
                ),
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "blocks": [
                        {
                            "block_id": "review-1",
                            "type": "text",
                            "text": (
                                "Reviews heavily reinforce consumer preference "
                                "for smooth, soft pâté textures."
                            ),
                        },
                        {
                            "block_id": "review-2",
                            "type": "text",
                            "text": (
                                "Reviews indicate consumer friction directly "
                                "related to the packaging, specifically regarding "
                                "difficulty opening the seal."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    statuses_by_family = {
        item["claim_family"]: item["status"]
        for item in payload["claims"]
        if item["claim_family"] in {"review_validation", "review_friction"}
    }
    assert payload["summary"]["unresolved_count"] == 0
    assert statuses_by_family == {
        "review_validation": "verified",
        "review_friction": "verified",
    }
    review_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "review_validation"
    )
    support = review_claim["details"]["row_support"][0]
    assert support["anchor_tokens"] == ["pate"]
    assert support["positive_match_count"] == 4
    assert set(support["positive_support"]) == {"comfort", "texture"}
    assert all(
        {row["bundle_label"] for row in rows} == {"Pate + Can"}
        for rows in support["positive_support"].values()
    )


def test_validate_launch_report_pdf_uses_ranked_bundle_evidence_for_texture_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(package_dir / "recent_products.csv", [])
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Pet Brand Alpha Classic Seafood Variety Pack",
                "brand": "Pet Brand Alpha",
                "pareto_rank": 3,
                "pareto_bucket": "A",
                "food texture": "Pate",
                "packaging type": "Can",
            },
            {
                "product_name": "Pet Brand Beta Seafood and Chicken Pate",
                "brand": "Pet Brand Beta",
                "pareto_rank": 5,
                "pareto_bucket": "A",
                "food texture": "Pate",
                "packaging type": "Can",
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "blocks": [
                        {
                            "block_id": "bundle-rank",
                            "type": "text",
                            "text": (
                                "Pate in Can: Signal Read Dominant Shelf Signal; "
                                "Visibility Metric Top-ranked products "
                                "(#3, #5 sellers)"
                            ),
                        },
                        {
                            "block_id": "summary",
                            "type": "text",
                            "text": (
                                "The actual drivers of shelf success are specific "
                                "texture formats."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summaries = [
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    ]
    assert payload["summary"]["unresolved_count"] == 0
    assert len(summaries) == 1
    assert summaries[0]["status"] == "partially_backed"
    assert summaries[0]["details"]["component_claims"][0]["claim_family"] == (
        "ranked_bundle_product_evidence"
    )


def test_validate_launch_report_pdf_does_not_use_unrelated_review_rows_for_health_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "bundle_review_validation.csv",
        [
            {
                "bundle_label": "Prescription + Health",
                "product_name": "Therapeutic Food",
                "reviews_positive_headline": "Smooth texture",
                "reviews_positive_comment": "Soft texture that cats prefer.",
                "reviews_negative_headline": "",
                "reviews_negative_comment": "",
            },
            {
                "bundle_label": "Prescription + Health",
                "product_name": "Therapeutic Food 2",
                "reviews_positive_headline": "Smooth texture",
                "reviews_positive_comment": "Soft texture and easy eating.",
                "reviews_negative_headline": "",
                "reviews_negative_comment": "",
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "blocks": [
                        {
                            "block_id": "review",
                            "type": "text",
                            "text": (
                                "Reviews heavily reinforce consumer preference "
                                "for smooth, soft pâté textures."
                            ),
                        }
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "blocks": [
                        {
                            "block_id": "health-summary",
                            "type": "text",
                            "text": (
                                "Prescription and therapeutic products appear in "
                                "top-seller reality, but do not represent a broad "
                                "health-need shift across the category."
                            ),
                        }
                    ],
                    "figure_regions": [],
                },
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["unresolved_count"] == 1
    review_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "review_validation"
    )
    assert review_claim["status"] == "contradicted"
    assert review_claim["details"]["row_support"][0]["anchor_tokens"] == ["pate"]
    assert review_claim["details"]["row_support"][0]["positive_match_count"] == 0
    assert payload["unresolved"][0]["claim_family"] == "summary_synthesis"


def test_validate_launch_report_pdf_reads_generation_source_sidecar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    source_package = {
        "package_dir": str(package_dir.resolve()),
        "retailer": "ulta",
        "category_key": "lipstick",
        "category_label": "lipstick",
        "content_fingerprint": validator.build_launch_package_content_fingerprint(
            package_dir
        ),
    }
    pdf_path.with_suffix(".launch_report_source.json").write_text(
        json.dumps(
            {
                "version": "launch_report_source/1",
                "pptx_file": "lipstick.pptx",
                "report_payload_file": "report_payload.json",
                "source_package": source_package,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: _fake_reading_payload(),
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    generation_source = payload["generation_source"]
    assert generation_source["status"] == "matched_current_package"
    assert generation_source["source_package"] == source_package
    assert generation_source["package_fingerprint_matches_current"] is True


def test_validate_launch_report_pdf_verifies_cohort_count_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "count-1",
                            "type": "text",
                            "text": (
                                "A factual synthesis of 1 top-selling product "
                                "and 1 recent launch."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["verified_count"] == 1
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "cohort_count"
    assert claim["details"]["cohort_labels"] == ["top_seller", "recent"]
    assert claim["details"]["count_values"] == {"top_seller": 1, "recent": 1}
    assert claim["details"]["package_values"]["cohort_counts"] == {
        "top_seller": 1,
        "recent": 1,
    }
    assert claim["details"]["source_basis"] == {
        "recent": "recent_products.csv",
        "top_seller": "top_seller_products.csv",
    }
    assert "exact equality" in claim["details"]["comparison_policy"]


def test_validate_launch_report_pdf_contradicts_wrong_cohort_count_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "count-1",
                            "type": "text",
                            "text": (
                                "A factual synthesis of 2 top-selling products "
                                "and 1 recent launch."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "cohort_count"
    assert claim["details"]["count_values"] == {"top_seller": 2, "recent": 1}
    assert claim["details"]["package_values"]["cohort_counts"] == {
        "top_seller": 1,
        "recent": 1,
    }
    assert claim["details"]["reasons"] == [
        "top_seller count mismatch: expected 1, observed 2"
    ]


def test_validate_launch_report_pdf_verifies_recent_top_seller_overlap_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "recent_products.csv",
        [
            {
                "canonical_id_export": "product-a",
                "product_name": "Recent Winner A",
                "brand": "Brand A",
            },
            {
                "canonical_id_export": "product-c",
                "product_name": "Recent Winner C",
                "brand": "Brand C",
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "canonical_id_export": "product-a",
                "product_name": "Recent Winner A",
                "brand": "Brand A",
                "pareto_rank": 1,
            },
            {
                "canonical_id_export": "product-b",
                "product_name": "Classic Winner B",
                "brand": "Brand B",
                "pareto_rank": 2,
            },
            {
                "canonical_id_export": "product-c",
                "product_name": "Recent Winner C",
                "brand": "Brand C",
                "pareto_rank": 3,
            },
            {
                "canonical_id_export": "product-d",
                "product_name": "Classic Winner D",
                "brand": "Brand D",
                "pareto_rank": 4,
            },
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "overlap-1",
                            "type": "text",
                            "text": (
                                "The recent and top-seller cohorts act as distinct "
                                "lanes; only 2 of the top 3 products overlap "
                                "between windows."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "cohort_overlap"
    assert claim["details"]["observed_values"] == {
        "overlap_count": 2,
        "top_window_count": 3,
    }
    assert claim["details"]["package_values"]["overlap_count"] == 2
    assert claim["details"]["package_values"]["identity_column"] == (
        "canonical_id_export"
    )
    assert claim["details"]["matched_row_keys"] == {
        "identity_column": "canonical_id_export"
    }
    assert "exact equality" in claim["details"]["comparison_policy"]


def test_validate_launch_report_pdf_verifies_ranked_recent_top_seller_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "brand": "Pet Brand Beta",
                "product_name": "Pet Brand Beta Chicken Pate",
                "pareto_rank": 81,
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "canonical_id_export": "pet-brand-beta-81",
            },
            {
                "brand": "Pet Brand Beta",
                "product_name": "Pet Brand Beta Gravy Variety Pack",
                "pareto_rank": 91,
                "listing_status": "recent",
                "top_seller_status": "top_seller",
                "canonical_id_export": "pet-brand-beta-91",
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "overlap-1",
                            "type": "text",
                            "text": (
                                "However, this alignment includes recent products "
                                "that are already top sellers (Pet Brand Beta ranking "
                                "#81 and #91)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["unresolved_count"] == 0
    assert len(payload["claims"]) == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "cohort_overlap"
    assert claim["entity"] == "ranked_recent_top_seller_overlap"
    assert claim["details"]["observed_values"] == {
        "brand": "Pet Brand Beta",
        "ranks": [81, 91],
    }
    assert claim["details"]["matched_row_keys"] == {
        "brand": "Pet Brand Beta",
        "pareto_rank": [81, 91],
    }
    assert len(claim["details"]["package_values"]["matched_products"]) == 2


def test_validate_launch_report_pdf_partially_backs_brand_overindex_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "Brand Aurora",
                "catalog_count": 4,
                "top_seller_count": 4,
                "catalog_share": 0.0118,
                "top_seller_share_of_cohort": 0.0588,
                "over_index_vs_catalog_share": 4.98,
            },
            {
                "brand": "Brand Mosaic",
                "catalog_count": 1,
                "top_seller_count": 1,
                "catalog_share": 0.0029,
                "top_seller_share_of_cohort": 0.0147,
                "over_index_vs_catalog_share": 5.07,
            },
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-1",
                            "type": "text",
                            "text": (
                                "Brand Aurora and Brand Mosaic heavily over-index in "
                                "top sellers."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    claim = payload["claims"][0]
    assert claim["status"] == "partially_backed"
    assert claim["claim_family"] == "brand_share"
    assert claim["entity"] == "Brand Aurora, Brand Mosaic"
    assert claim["details"]["observed_values"]["intensity_qualifier_present"] is True
    assert claim["details"]["matched_row_keys"] == {
        "brands": ["Brand Aurora", "Brand Mosaic"]
    }
    assert [
        item["over_index_vs_catalog_share"]
        for item in claim["details"]["package_values"]["brand_support"]
    ] == [4.98, 5.07]


def test_validate_launch_report_pdf_matches_short_brand_alias_overindex_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "Delta Cosmetics",
                "catalog_count": 4,
                "top_seller_count": 3,
                "catalog_share": 0.0223,
                "top_seller_share_of_cohort": 0.0833,
                "over_index_vs_catalog_share": 3.73,
            },
            {
                "brand": "Brand Mosaic",
                "catalog_count": 2,
                "top_seller_count": 2,
                "catalog_share": 0.0112,
                "top_seller_share_of_cohort": 0.0556,
                "over_index_vs_catalog_share": 4.97,
            },
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-1",
                            "type": "text",
                            "text": "Delta and Brand Mosaic heavily over-index in top sellers.",
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    brand_claims = [
        item for item in payload["claims"] if item["claim_family"] == "brand_share"
    ]
    assert len(brand_claims) == 1
    assert brand_claims[0]["status"] == "partially_backed"
    assert brand_claims[0]["entity"] == "Delta Cosmetics, Brand Mosaic"
    assert brand_claims[0]["details"]["matched_row_keys"] == {
        "brands": ["Delta Cosmetics", "Brand Mosaic"]
    }
    assert not any(
        item["claim_family"] == "brand_share" for item in payload["unresolved"]
    )


def test_validate_launch_report_pdf_matches_short_single_brand_alias_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "Beacon Cosmetics",
                "catalog_count": 8,
                "top_seller_count": 4,
                "catalog_share": 0.0391,
                "top_seller_share_of_cohort": 0.1111,
                "over_index_vs_catalog_share": 2.84,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-1",
                            "type": "text",
                            "text": (
                                "Beacon holds 4 top sellers out of 8 catalog "
                                "products (10.8% of the top-seller cohort)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "brand_share"
    assert claim["entity"] == "Beacon Cosmetics"
    assert claim["details"]["matched_row_keys"] == {"brand": "Beacon Cosmetics"}
    assert claim["details"]["observed_values"]["cohort_counts"] == {"top_seller": 4}


def test_validate_launch_report_pdf_verifies_recent_directional_attribute_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "filter_comparison.csv",
        [
            {
                "filter_family": "coverage",
                "filter_value": "full",
                "count_recent": 6,
                "count_rest": 61,
                "recent_family_base": 56,
                "rest_family_base": 209,
                "pct_recent": 0.1071428571,
                "pct_rest": 0.2918660287,
                "delta": -0.1847231716,
            },
            {
                "filter_family": "finish",
                "filter_value": "matte",
                "count_recent": 19,
                "count_rest": 92,
                "recent_family_base": 63,
                "rest_family_base": 243,
                "pct_recent": 0.3015873016,
                "pct_rest": 0.3786008230,
                "delta": -0.0770135214,
            },
        ],
    )
    _write_csv(
        package_dir / "resolved_core_comparison.csv",
        [
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "Full",
                "count_recent": 1,
                "count_rest": 31,
                "recent_base": 67,
                "rest_base": 266,
                "pct_recent": 0.0149253731,
                "pct_rest": 0.1165413534,
                "delta": -0.1016159803,
            }
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "direction-1",
                            "type": "text",
                            "text": (
                                "Recent filter QA indicates a divergence, with "
                                "recent products strictly leaning away from full "
                                "coverage and matte finishes."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "attribute_direction"
    assert claim["details"]["cohort_basis"] == "recent_vs_rest"
    assert claim["details"]["component_entities"] == ["full", "matte"]
    assert [item["source_file"] for item in claim["details"]["attribute_support"]] == [
        "filter_comparison.csv",
        "filter_comparison.csv",
    ]


def test_validate_launch_report_pdf_verifies_top_seller_directional_attribute_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "ethical claims",
                "attribute_value": "Cruelty-free",
                "count_top_seller": 18,
                "count_other": 39,
                "top_seller_base": 21,
                "other_base": 78,
                "pct_top_seller": 0.8571428571,
                "pct_other": 0.5,
                "delta": 0.3571428571,
            },
            {
                "attribute_name": "ethical claims",
                "attribute_value": "Vegan",
                "count_top_seller": 3,
                "count_other": 39,
                "top_seller_base": 21,
                "other_base": 78,
                "pct_top_seller": 0.1428571429,
                "pct_other": 0.5,
                "delta": -0.3571428571,
            },
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "direction-1",
                            "type": "text",
                            "text": (
                                "Cruelty-free over-indexes in top sellers, "
                                "but vegan under-indexes."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "attribute_direction"
    assert claim["details"]["cohort_basis"] == "top_seller_vs_other"
    assert claim["details"]["component_entities"] == ["Cruelty-free", "Vegan"]
    assert [
        item["claimed_direction"] for item in claim["details"]["attribute_support"]
    ] == ["positive", "negative"]


def test_validate_launch_report_pdf_verifies_flat_top_seller_attribute_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "ethics claims",
                "attribute_value": "Cruelty-free",
                "count_top_seller": 28,
                "count_other": 116,
                "top_seller_base": 45,
                "other_base": 174,
                "pct_top_seller": 0.6222222222,
                "pct_other": 0.6666666667,
                "delta": -0.0444444445,
            },
            {
                "attribute_name": "ethics claims",
                "attribute_value": "Clean",
                "count_top_seller": 9,
                "count_other": 34,
                "top_seller_base": 45,
                "other_base": 174,
                "pct_top_seller": 0.2,
                "pct_other": 0.1954022989,
                "delta": 0.0045977011,
            },
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "flat-ethics",
                            "type": "text",
                            "text": (
                                "Clean/Ethical claims are flat: Cruelty-free "
                                "presence is flat among top-sellers, and "
                                '"clean" claims do not form a central winning bundle.'
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "attribute_direction"
    assert claim["details"]["cohort_basis"] == "top_seller_vs_other"
    assert claim["details"]["component_entities"] == ["Cruelty-free", "Clean"]
    assert [
        item["claimed_direction"] for item in claim["details"]["attribute_support"]
    ] == ["flat", "flat"]
    assert claim["details"]["threshold_policy"]["flat_delta_abs_max"] == 0.05


def test_validate_launch_report_pdf_does_not_treat_flat_bundle_row_as_attribute_direction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "life_stage=adult + special_diet=grain-free",
                "bundle_label": "Adult + Grain-Free",
                "count_top_seller": 20,
                "count_other": 60,
                "top_seller_base": 65,
                "other_base": 196,
                "pct_top_seller": 0.3076923077,
                "pct_other": 0.3061224490,
                "top_seller_brand_count": 8,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "flat-bundle",
                            "type": "text",
                            "text": (
                                'The "Adult + Grain-Free" bundle accounts for '
                                "30.8% of top sellers versus 30.6% of all other "
                                "products, remaining essentially flat."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["verified_count"] == 1
    assert payload["claims"][0]["claim_family"] == "bundle_metric"
    assert all(
        item["claim_family"] != "attribute_direction" for item in payload["unresolved"]
    )


def test_validate_launch_report_pdf_verifies_no_single_category_brand_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "Brand Vale",
                "catalog_count": 15,
                "top_seller_count": 4,
                "catalog_share": 0.0785340314,
                "top_seller_share_of_cohort": 0.1025641026,
                "over_index_vs_catalog_share": 1.3059829060,
            },
            {
                "brand": "House Label",
                "catalog_count": 16,
                "top_seller_count": 4,
                "catalog_share": 0.0837696335,
                "top_seller_share_of_cohort": 0.1025641026,
                "over_index_vs_catalog_share": 1.2243589744,
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-6",
                    "slide_number": 6,
                    "page_number": 6,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-1",
                            "type": "text",
                            "text": (
                                "While clear over-indexing exists, no single "
                                "house owns the category."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "category_brand_concentration"
    assert claim["entity"] == "Brand Vale"
    assert claim["details"]["package_values"][
        "dominant_brand_share_pct"
    ] == pytest.approx(10.25641026)
    assert claim["details"]["package_values"]["over_indexed_brand_count"] == 2


def test_validate_launch_report_pdf_partially_backs_brand_artifact_survival(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "Beacon Cosmetics",
                "catalog_count": 7,
                "top_seller_count": 4,
                "catalog_share": 0.0391061453,
                "top_seller_share_of_cohort": 0.1111111111,
                "over_index_vs_catalog_share": 2.8412698413,
            },
            {
                "brand": "Two Tone Cosmetics",
                "catalog_count": 3,
                "top_seller_count": 3,
                "catalog_share": 0.0167597765,
                "top_seller_share_of_cohort": 0.0833333333,
                "over_index_vs_catalog_share": 4.9722222222,
            },
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-1",
                            "type": "text",
                            "text": (
                                "The core winning signals survive brand concentration."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    claim = payload["claims"][0]
    assert claim["status"] == "partially_backed"
    assert claim["claim_family"] == "category_brand_concentration"
    assert claim["details"]["comparison_outcome"] == "partial"
    assert (
        claim["details"]["threshold_policy"]["scope"]
        == "whole top-seller cohort, not bundle-specific signal rows"
    )


def test_validate_launch_report_pdf_fails_on_contradicted_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-1",
                            "type": "text",
                            "text": "BRAND ALPHA is 20.0% of the top-seller cohort from 8.0% of catalog share (1.38x over-index).",
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    assert payload["claims"][0]["claim_family"] == "brand_share"
    assert payload["claims"][0]["status"] == "contradicted"
    assert payload["claims"][0]["details"]["observed_values"]["percents"] == [20.0, 8.0]
    assert (
        payload["claims"][0]["details"]["package_values"][
            "top_seller_share_of_cohort_pct"
        ]
        == 11.0
    )


def test_validate_launch_report_pdf_does_not_apply_attribute_percents_to_brand_list(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-list-1",
                            "type": "text",
                            "text": (
                                "Cruelty-free claims lift in top sellers "
                                "(72.4% vs 56.1%), but this is carried by "
                                "specific over-indexed brands (BRAND ALPHA)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["contradicted_count"] == 0
    assert payload["unresolved"][0]["claim_family"] == "brand_share"
    assert (
        payload["unresolved"][0]["details"]["message"]
        == "numeric evidence is not local to the matched brand"
    )


def test_validate_launch_report_pdf_routes_brand_roster_before_bundle_metric(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "House Label",
                "catalog_share": 0.08377,
                "top_seller_count": 11,
                "top_seller_share_of_cohort": 11 / 96,
                "over_index_vs_catalog_share": 1.3684,
            },
            {
                "brand": "Brand Vale",
                "catalog_share": 0.083,
                "top_seller_count": 4,
                "top_seller_share_of_cohort": 4 / 39,
                "over_index_vs_catalog_share": 1.2357,
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-roster",
                            "type": "bullet_item",
                            "text": (
                                "House Label: 11.5% (11/96 top sellers) "
                                "Brand Vale: 8.3% (8/96 top sellers)"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    brand_claims = [
        item for item in payload["claims"] if item["claim_family"] == "brand_share"
    ]
    assert [item["entity"] for item in brand_claims] == ["House Label", "Brand Vale"]
    assert [item["status"] for item in brand_claims] == ["verified", "contradicted"]
    assert brand_claims[0]["details"]["package_values"]["top_seller_base"] == 96
    assert (
        "brand top-seller count/base mismatch"
        in brand_claims[1]["details"]["reasons"][1]
    )
    assert not any(
        item["claim_family"] == "bundle_metric" for item in payload["unresolved"]
    )


def test_validate_launch_report_pdf_keeps_bundle_route_when_brand_hint_has_no_brand(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "Minced + Sensitive Digestion",
                "count_recent": 6,
                "recent_base": 633,
                "count_rest": 1,
                "rest_base": 2531,
                "pct_recent": 0.009478672985781991,
                "pct_rest": 0.0003951007506914263,
                "prevalence_ratio": 23.9905,
                "recent_brand_count": 2,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-overindex",
                            "type": "bullet_item",
                            "text": (
                                "Combinations like Minced + Sensitive Digestion show "
                                "massive over-indexing (31.99x ratio), but remain "
                                "confined to a 2-brand footprint."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    bundle_claim = next(
        item for item in payload["claims"] if item["claim_family"] == "bundle_metric"
    )
    assert bundle_claim["status"] == "contradicted"
    assert bundle_claim["entity"] == "Minced + Sensitive Digestion"
    assert bundle_claim["details"]["reasons"] == ["ratio mismatch: expected 23.99x"]
    assert not any(
        item["claim_family"] == "brand_share" for item in payload["unresolved"]
    )


def test_validate_launch_report_pdf_marks_selected_bundle_candidate_first(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Duck + Sensitive Digestion",
                "count_top_seller": 5,
                "top_seller_base": 633,
                "count_other": 14,
                "other_base": 2531,
                "pct_top_seller": 0.0078988941548183,
                "pct_other": 0.0055314105096799,
                "top_seller_brand_count": 4,
                "other_brand_count": 9,
                "prevalence_ratio": 1.428,
            }
        ],
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "Duck + Sensitive Digestion",
                "count_recent": 7,
                "recent_base": 633,
                "count_rest": 12,
                "rest_base": 2531,
                "pct_recent": 0.0110584518167457,
                "pct_rest": 0.0047412090082971,
                "recent_brand_count": 5,
                "rest_brand_count": 8,
                "prevalence_ratio": 2.3324,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "duck-sensitive",
                            "type": "text",
                            "text": (
                                "Duck + Sensitive Digestion: Evidence Ratio "
                                "4.66x; Brand Spread 5 brands; Read Small, "
                                "but cross-brand credible"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item for item in payload["claims"] if item["claim_family"] == "bundle_metric"
    )
    assert claim["status"] == "contradicted"
    assert claim["details"]["source_file"] == "innovation_pairs.csv"
    candidate_evaluations = claim["details"]["candidate_evaluations"]
    assert candidate_evaluations[0]["selected_candidate"] is True
    assert candidate_evaluations[0]["file"] == "innovation_pairs.csv"
    assert candidate_evaluations[0]["matched_metrics"] == ["brand_count"]
    assert candidate_evaluations[1]["selected_candidate"] is False


def test_validate_launch_report_pdf_without_package_match_still_writes_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "lip_balm.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_prefix = tmp_path / "validation" / "lip_balm"

    def _unexpected_reading(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("PDF reading should not run without a source package")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        _unexpected_reading,
    )

    payload = validator.validate_launch_report_pdf(
        pdf_path,
        package_roots=(tmp_path / "packages" / "launch",),
        llm_review=True,
    )

    assert payload["status"] == "fail"
    assert payload["summary"]["slide_count"] == 0
    assert payload["resolver"]["status"] == "unresolved"
    assert payload["reading_quality"]["status"] == "not_run"
    assert "llm_review" not in payload

    json_path, md_path = validator.write_launch_report_validation_artifacts(
        payload=payload,
        output_prefix=output_prefix,
    )

    assert json_path.exists()
    markdown = md_path.read_text(encoding="utf-8")
    assert "Slides visited: `0`" in markdown
    assert "no matching launch package" in markdown.lower()
    assert "PDF reading/OCR was not run" in markdown
    assert "Reading quality: `not_run`" in markdown


def test_validate_launch_report_pdf_treats_parent_summary_without_briefs_as_not_validated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    brief_root = tmp_path / "briefs" / "launch"
    pdf_path = tmp_path / "permanent.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    def _unexpected_reading(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("parent summary reports should not run PDF reading")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        _unexpected_reading,
    )

    payload = validator.validate_launch_report_pdf(
        pdf_path,
        package_roots=(tmp_path / "packages",),
        brief_roots=(brief_root,),
    )

    assert payload["status"] == "not_validated"
    assert payload["report_type"] == "summary_report"
    assert payload["resolver"]["status"] == "summary_report"
    assert payload["resolver"]["missing_brief_count"] == 2
    assert payload["summary"]["slide_count"] == 0
    assert payload["reading_quality"]["status"] == "not_run"
    unresolved_families = {item["claim_family"] for item in payload["unresolved"]}
    assert unresolved_families == {
        "summary_report_validation",
        "summary_child_brief",
    }


def test_validate_launch_report_pdf_treats_ulta_parent_reports_as_summaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    brief_root = tmp_path / "briefs" / "launch"

    def _unexpected_reading(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("parent summary reports should not run PDF reading")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        _unexpected_reading,
    )

    expected_missing_counts = {
        "lips_ulta": 8,
        "face_ulta": 12,
    }
    for stem, expected_missing_count in expected_missing_counts.items():
        pdf_path = tmp_path / f"{stem}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")

        payload = validator.validate_launch_report_pdf(
            pdf_path,
            package_roots=(tmp_path / "packages",),
            brief_roots=(brief_root,),
        )

        assert payload["status"] == "not_validated"
        assert payload["report_type"] == "summary_report"
        assert payload["resolver"]["status"] == "summary_report"
        assert payload["resolver"]["missing_brief_count"] == expected_missing_count


def test_validate_launch_report_pdf_checks_parent_summary_against_child_briefs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    brief_root = tmp_path / "briefs" / "launch"
    for retailer in ("cosmoprofbeauty", "saloncentric"):
        (brief_root / retailer).mkdir(parents=True)
        (brief_root / retailer / "permanent.md").write_text(
            "\n".join(
                [
                    "# Permanent brief",
                    "Grey coverage + cream appears in 55.6% of top sellers vs 30.9% of others.",
                    "The category is anchored by grey coverage and cream formats.",
                ]
            ),
            encoding="utf-8",
        )
    pdf_path = tmp_path / "permanent.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "permanent",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "blocks": [
                        {
                            "block_id": "num-ok",
                            "type": "text",
                            "text": "Grey coverage + cream appears in 55.6% of top sellers vs 30.9% of others.",
                        },
                        {
                            "block_id": "qual-ok",
                            "type": "text",
                            "text": "The category is anchored by grey coverage and cream formats.",
                        },
                        {
                            "block_id": "num-missing",
                            "type": "text",
                            "text": "A different structure appears in 88.8% of recent products.",
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(
        pdf_path,
        package_roots=(tmp_path / "packages",),
        brief_roots=(brief_root,),
    )

    assert payload["status"] == "fail"
    assert payload["report_type"] == "summary_report"
    assert payload["summary"]["verified_count"] == 1
    assert payload["summary"]["weakly_backed_count"] == 1
    assert payload["summary"]["contradicted_count"] == 1
    assert payload["summary_report"]["available_brief_count"] == 2
    assert payload["reading_quality"]["status"] == "read_ok"
    assert {claim["claim_family"] for claim in payload["claims"]} == {
        "summary_numeric_claim",
        "summary_qualitative_claim",
    }


def test_validate_launch_report_pdf_marks_sparse_reading_as_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_balm",
        category_label="lip balm",
    )
    pdf_path = tmp_path / "lip_balm.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_balm",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "title_text": "",
                    "bullet_texts": [],
                    "ocr_text": "tiny",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": "tiny",
                            "items": [],
                            "confidence": 0.41,
                            "audit_status": "suspicious",
                        },
                        {
                            "block_id": "block-2",
                            "type": "chart",
                            "text": "",
                            "items": [],
                            "visual_status": "uncertain",
                            "visual_confidence": 0.52,
                        },
                    ],
                    "figure_regions": [{"x": 1.0, "y": 1.0, "w": 2.0, "h": 2.0}],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["claim_count"] == 0
    assert payload["summary"]["unresolved_count"] == 0
    assert payload["summary"]["image_region_count"] == 1
    assert payload["reading_quality"]["status"] == "read_warning"
    assert payload["reading_quality"]["summary"]["warning_slide_count"] == 1
    assert payload["reading_quality"]["flagged_slides"][0]["slide_number"] == 1
    assert any(
        "suspicious" in reason
        for reason in payload["reading_quality"]["flagged_slides"][0]["reasons"]
    )


def test_validate_launch_report_pdf_surfaces_reading_completeness_warnings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "Plain overview text only",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": "Plain overview text only",
                        }
                    ],
                    "figure_regions": [],
                }
            ],
            "reading_completeness": {
                "status": "read_warning",
                "summary": {
                    "slide_count": 1,
                    "flagged_slide_count": 1,
                    "missing_ocr_line_count": 2,
                    "ocr_line_count": 4,
                    "layout_text_region_count": 4,
                    "analysis_text_unit_count": 1,
                    "layout_available": True,
                    "ocr_available": True,
                },
                "reasons": ["1 slide(s) showed stage-to-stage reading gaps"],
                "flagged_slides": [
                    {
                        "slide_number": 1,
                        "slide_id": "slide-1",
                        "status": "read_warning",
                        "missing_ocr_line_count": 2,
                        "reasons": [
                            "2 OCR text line(s) were not preserved in slide analysis"
                        ],
                    }
                ],
            },
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["claim_count"] == 0
    assert payload["reading_quality"]["status"] == "read_warning"
    assert (
        payload["reading_quality"]["summary"]["completeness_status"] == "read_warning"
    )
    assert payload["reading_quality"]["summary"]["missing_ocr_line_count"] == 2
    assert (
        payload["reading_quality"]["completeness"]["flagged_slides"][0]["slide_number"]
        == 1
    )


def test_validate_launch_report_pdf_bundle_contradiction_includes_package_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": "Pink + stick form: Recent (%) 99.0%; Rest (%) 1.0%",
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["details"]["observed_values"]["percents"] == [99.0, 1.0]
    assert claim["details"]["matched_row_keys"]["bundle_label"] == "pink + stick"
    assert claim["details"]["package_values"]["bundle_label"] == "pink + stick"
    assert claim["details"]["reasons"] == [
        "recent percent mismatch: expected 46.7%",
        "rest percent mismatch: expected 43.2%",
    ]
    candidate = claim["details"]["candidate_evaluations"][0]
    assert candidate["file"] == "innovation_pairs.csv"
    assert candidate["matched_row_keys"]["bundle_label"] == "pink + stick"
    assert candidate["package_values"]["bundle_label"] == "pink + stick"
    assert candidate["package_values"]["pct_recent"] == 46.7
    assert candidate["package_values"]["pct_rest"] == 43.2


def test_validate_launch_report_pdf_bundle_contradiction_uses_closest_failed_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "lifestage=Adult + subtype=Grain-Free",
                "bundle_label": "Adult + Grain-Free",
                "count_top_seller": 27,
                "count_other": 150,
                "top_seller_base": 633,
                "other_base": 1957,
                "pct_top_seller": 0.0426540284,
                "pct_other": 0.0766479305,
                "top_seller_brand_count": 8,
            },
            {
                "bundle_key": "lifestage=adult + special_diet=Grain-Free",
                "bundle_label": "Adult + Grain-Free",
                "count_top_seller": 224,
                "count_other": 671,
                "top_seller_base": 633,
                "other_base": 1957,
                "pct_top_seller": 0.3538704581,
                "pct_other": 0.3428717425,
                "top_seller_brand_count": 29,
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Adult + Grain-Free: 30.8% of top sellers versus "
                                "30.6% of all other products."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["status"] == "contradicted"
    assert claim["details"]["package_values"]["count_top_seller"] == 224
    assert claim["details"]["package_values"]["top_seller_brand_count"] == 29
    assert claim["details"]["package_values"]["pct_top_seller"] == pytest.approx(
        35.38704581
    )
    assert claim["details"]["package_values"]["pct_other"] == pytest.approx(34.28717425)
    assert claim["details"]["numeric_distance_from_claim"] == pytest.approx(8.27422006)
    assert claim["details"]["reasons"] == [
        "top_seller percent mismatch: expected 35.4%",
        "other percent mismatch: expected 34.3%",
    ]


def test_validate_launch_report_pdf_partially_backs_bundle_when_one_percent_role_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Hydrating + Buildable + Stick form",
                "count_top_seller": 3,
                "top_seller_base": 36,
                "count_other": 1,
                "other_base": 143,
                "pct_top_seller": 0.0833333333,
                "pct_other": 0.006993007,
                "prevalence_ratio": 11.9167,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Hydrating + Buildable + Stick form; Market Signal "
                                "8.1% vs 0.7%"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = payload["claims"][0]
    assert claim["status"] == "partially_backed"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["details"]["matched_metrics"] == ["other_percent"]
    assert claim["details"]["mismatched_metrics"] == ["top_seller_percent"]
    assert claim["details"]["reasons"] == ["top_seller percent mismatch: expected 8.3%"]
    diagnostics = claim["details"]["numeric_basis_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["role"] == "top_seller"
    assert diagnostics[0]["observed_percent"] == 8.1
    assert diagnostics[0]["expected_percent"] == pytest.approx(8.33333333)
    assert diagnostics[0]["current_count"] == 3
    assert diagnostics[0]["current_base"] == 36
    assert diagnostics[0]["implied_base_if_current_count_held"] == 37
    assert diagnostics[0]["implied_count_if_current_base_held"] == 3


def test_validate_launch_report_pdf_matches_role_labeled_bundle_percent_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Adult + Grain-Free",
                "count_top_seller": 224,
                "count_other": 671,
                "top_seller_base": 633,
                "other_base": 1957,
                "pct_top_seller": 0.3538704581,
                "pct_other": 0.3428717425,
                "top_seller_brand_count": 29,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Adult + Grain-Free: 34.3% of all other products "
                                "versus 35.4% of top sellers."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["details"]["package_values"]["pct_top_seller"] == pytest.approx(
        35.38704581
    )
    assert claim["details"]["package_values"]["pct_other"] == pytest.approx(34.28717425)


def test_validate_launch_report_pdf_filters_briefing_and_scope_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "briefing-1",
                            "type": "body_text",
                            "text": (
                                "Evidence Briefing: Top Sellers, Web-Shelf "
                                "Architecture, and Emerging Innovation Cohorts"
                            ),
                        },
                        {
                            "block_id": "scope-1",
                            "type": "footer_meta",
                            "text": (
                                "Data Scope: Sell-out baseline, rank-weighted "
                                "visibility, and recent product cohorts. "
                                "Document Focus: Findings and diagnostic validation."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["unresolved_count"] == 0
    assert payload["summary"]["non_claim_count"] == 2
    assert {item["details"]["filter_rule_id"] for item in payload["non_claims"]} == {
        "NF08",
        "NF09",
    }


def test_validate_launch_report_pdf_checks_market_signal_bundle_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Blurring/Smoothing + Pressed powder",
                "count_top_seller": 5,
                "count_other": 9,
                "top_seller_base": 37,
                "other_base": 164,
                "pct_top_seller": 0.1351351351,
                "pct_other": 0.0548780488,
                "top_seller_brand_count": 5,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "table-1",
                            "type": "table",
                            "table_model": {
                                "header_rows": 0,
                                "rows": [
                                    {
                                        "cells": [
                                            {
                                                "text": (
                                                    "Secondary Lane: Dominant "
                                                    "Attributes Blurring/Smoothing "
                                                    "+ Pressed powder"
                                                )
                                            },
                                            {
                                                "text": (
                                                    "Market Signal 13.5% vs 5.5%, "
                                                    "across 5 brands"
                                                )
                                            },
                                        ]
                                    }
                                ],
                            },
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "Blurring/Smoothing + Pressed powder"
    assert claim["file"] == "top_seller_pairs.csv"
    assert claim["details"]["observed_values"]["percents"] == [13.5, 5.5]
    assert claim["details"]["observed_values"]["brand_count"] == 5
    assert claim["details"]["denominators"] == {"top_seller": 37, "other": 164}


def test_validate_launch_report_pdf_checks_evidence_ratio_brand_spread_bundle_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "Sensitive Digestion + Adult",
                "count_recent": 38,
                "count_rest": 89,
                "recent_base": 633,
                "rest_base": 2531,
                "pct_recent": 0.0600315956,
                "pct_rest": 0.035164,
                "recent_brand_count": 7,
                "rest_brand_count": 26,
                "prevalence_ratio": 1.88,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "evidence-ratio-1",
                            "type": "text",
                            "text": (
                                "Sensitive Digestion + Adult: Evidence Ratio 1.88x; "
                                "Brand Spread 7 brands; Read Broadest functional signal"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "Sensitive Digestion + Adult"
    assert claim["details"]["observed_values"]["ratios"] == [1.88]
    assert claim["details"]["observed_values"]["brand_count"] == 7


def test_validate_launch_report_pdf_accepts_unqualified_brand_spread_across_roles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "Sensitive Digestion + Adult",
                "count_recent": 38,
                "count_rest": 89,
                "recent_base": 633,
                "rest_base": 2531,
                "pct_recent": 0.0600315956,
                "pct_rest": 0.035164,
                "recent_brand_count": 7,
                "rest_brand_count": 26,
                "prevalence_ratio": 1.88,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "evidence-ratio-1",
                            "type": "text",
                            "text": (
                                "Sensitive Digestion + Adult: Evidence Ratio 1.88x; "
                                "Brand Spread 26 brands"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["details"]["observed_values"]["brand_count"] == 26
    assert claim["details"]["package_values"]["rest_brand_count"] == 26


def test_validate_launch_report_pdf_rejects_secondary_only_bundle_metric_support(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "brand": "Brand North",
                "top_seller_status": "top_seller",
                "neckline": "crewneck",
                "sleeve length_mapped": "long sleeve",
                "knit_detail": "rib-knit",
            },
            {
                "brand": "Brand Vale",
                "top_seller_status": "top_seller",
                "neckline": "crewneck",
                "sleeve length_mapped": "long sleeve",
                "knit_detail": "rib-knit",
            },
            {
                "brand": "Brand Vale",
                "top_seller_status": "other",
                "neckline": "crewneck",
                "sleeve length_mapped": "long sleeve",
                "knit_detail": "rib-knit",
            },
            {
                "brand": "Brand South",
                "top_seller_status": "other",
                "neckline": "crewneck",
                "sleeve length_mapped": "long sleeve",
                "knit_detail": "rib-knit",
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "rib-knit + crewneck + long sleeve: Top-Seller "
                                "Penetration 50.0%; Brand Breadth 3 brands"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["details"]["matched_metrics"] == ["brand_count"]
    assert claim["details"]["mismatched_metrics"] == ["top_seller_percent"]
    assert claim["details"]["package_values"]["all_brand_count"] == 3
    assert "brand-count mismatch" not in " ".join(claim["details"]["reasons"])


def test_validate_launch_report_pdf_checks_bundle_delta_percentage_points(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low top sneakers",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "lace-up + mesh",
                "count_recent": 11,
                "count_rest": 29,
                "recent_base": 47,
                "rest_base": 210,
                "pct_recent": 0.233,
                "pct_rest": 0.138,
                "delta": 0.083,
                "recent_brand_count": 13,
                "rest_brand_count": 15,
            }
        ],
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "lace-up + mesh: Recent Penetration 23.3%; "
                                "Rest Penetration 13.8%; Difference +9.5 pp; "
                                "Brand Breadth 13 brands"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    claim = payload["claims"][0]
    assert claim["status"] == "partially_backed"
    assert claim["details"]["observed_values"]["delta_pct_points"] == [9.5]
    assert claim["details"]["package_values"]["delta_pct_points"] == pytest.approx(8.3)
    assert claim["details"]["reasons"] == [
        "delta percentage-point mismatch: expected +8.3 pp"
    ]


def test_validate_launch_report_pdf_resolves_slash_alternative_bundle_labels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "striped + long sleeve",
                "count_recent": 3,
                "count_rest": 10,
                "recent_base": 39,
                "rest_base": 152,
                "pct_recent": 0.0769230769,
                "pct_rest": 0.0657894737,
                "delta": 0.0111336032,
                "recent_brand_count": 2,
            }
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-10",
                    "slide_number": 10,
                    "page_number": 10,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-slash",
                            "type": "text",
                            "text": (
                                "multicolor / striped + long sleeve: ~6-10% "
                                "recent penetration. Represents a pattern "
                                "expression, not a new silhouette."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "striped + long sleeve"
    assert claim["file"] == "innovation_pairs.csv"


def test_validate_launch_report_pdf_keeps_strict_triple_brand_span_exact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Long-wearing + Matte",
                "count_top_seller": 9,
                "count_other": 30,
                "top_seller_base": 37,
                "other_base": 164,
                "pct_top_seller": 0.2432432432,
                "pct_other": 0.1829268293,
                "top_seller_brand_count": 9,
            },
            {
                "bundle_label": "Matte + Pressed powder",
                "count_top_seller": 15,
                "count_other": 40,
                "top_seller_base": 37,
                "other_base": 164,
                "pct_top_seller": 0.4054054054,
                "pct_other": 0.243902439,
                "top_seller_brand_count": 13,
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Long-wearing + Matte + Pressed powder",
                "count_top_seller": 6,
                "count_other": 4,
                "top_seller_base": 37,
                "other_base": 164,
                "pct_top_seller": 0.1621621622,
                "pct_other": 0.0243902439,
                "top_seller_brand_count": 6,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "triple-1",
                            "type": "text",
                            "text": (
                                "The strictest triple (Long-wearing + Matte + "
                                "Pressed powder) is distributed across 6 "
                                "distinct brands."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    assert len(payload["claims"]) == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_brand_concentration"
    assert claim["entity"] == "Long-wearing + Matte + Pressed powder"
    assert claim["file"] == "top_seller_triples.csv"
    assert claim["details"]["brand_span"] == 6


def test_validate_launch_report_pdf_checks_rank_weighted_visibility_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Matte + Pressed powder",
                "count_top_seller": 14,
                "count_other": 30,
                "top_seller_base": 37,
                "other_base": 164,
                "pct_top_seller": 0.3783783784,
                "pct_other": 0.1829268293,
                "top_seller_brand_count": 11,
            }
        ],
    )
    _write_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 1,
                "bundle_key": "finish=natural + spf=no spf",
                "gross_weight_share": 0.552758,
                "incremental_weight_share": 0.552758,
                "cumulative_weight_share": 0.552758,
                "gross_sku_count": 50,
                "incremental_sku_count": 50,
                "density_index": 1.2,
            },
            {
                "alpha": 1.0,
                "shelf_rank": 2,
                "bundle_key": "form=pressed powder + spf=no spf",
                "gross_weight_share": 0.516315,
                "incremental_weight_share": 0.33005,
                "cumulative_weight_share": 0.882807,
                "gross_sku_count": 47,
                "incremental_sku_count": 30,
                "density_index": 1.1,
            },
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "visibility-1",
                            "type": "table",
                            "table_model": {
                                "header_rows": 0,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Pressed Powder + No SPF"},
                                            {"text": "Gross Weight 51.6%"},
                                            {"text": "Incremental Weight 33.0%"},
                                            {
                                                "text": (
                                                    "Structural Refinements Brings "
                                                    "cumulative selected weight to 88.3%."
                                                )
                                            },
                                        ]
                                    }
                                ],
                            },
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    assert {item["claim_family"] for item in payload["claims"]} == {
        "rank_weighted_visibility"
    }
    claim = payload["claims"][0]
    assert claim["claim_family"] == "rank_weighted_visibility"
    assert claim["entity"] == "form=pressed powder + spf=no spf"
    assert claim["file"] == "web_shelf_selected_shelves.csv"
    assert claim["details"]["observed_values"] == {
        "gross_weight_share_pct": 51.6,
        "incremental_weight_share_pct": 33.0,
        "cumulative_weight_share_pct": 88.3,
    }


def test_validate_launch_report_pdf_checks_contextual_incremental_visibility_cells(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 4,
                "bundle_key": "color=red + sleeve length=long sleeve",
                "gross_weight_share": 0.1248974713,
                "incremental_weight_share": 0.107,
                "cumulative_weight_share": 0.787733144,
                "gross_sku_count": 8,
                "incremental_sku_count": 5,
                "gross_brand_count": 7,
                "incremental_brand_count": 5,
                "top_brand_weight_share": 0.6226115978,
            },
            {
                "alpha": 1.0,
                "shelf_rank": 3,
                "bundle_key": "color=pink + sleeve length=long sleeve",
                "gross_weight_share": 0.1127274184,
                "incremental_weight_share": 0.12,
                "cumulative_weight_share": 0.6837106275,
                "gross_sku_count": 6,
                "incremental_sku_count": 5,
                "gross_brand_count": 5,
                "incremental_brand_count": 4,
                "top_brand_weight_share": 0.9278505052,
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "blockId": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Both are narrower than the core winning "
                                "architecture and highly concentrated."
                            ),
                        },
                        {
                            "blockId": "red-label",
                            "type": "group_label",
                            "text": "red + long sleeve",
                            "groupId": "red-group",
                            "groupKind": "exhibit",
                        },
                        {
                            "blockId": "pink-label",
                            "type": "group_label",
                            "text": "pink + long sleeve",
                            "groupId": "pink-group",
                            "groupKind": "exhibit",
                        },
                        {
                            "blockId": "red-metric",
                            "type": "body_text",
                            "text": "Incremental Visibility: 10.7%",
                            "parentId": "red-label",
                            "groupId": "red-group",
                            "groupKind": "exhibit",
                        },
                        {
                            "blockId": "pink-metric",
                            "type": "body_text",
                            "text": "Incremental Visibility: 12.0%",
                            "parentId": "pink-label",
                            "groupId": "pink-group",
                            "groupKind": "exhibit",
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    visibility_claims = [
        item
        for item in payload["claims"]
        if item["claim_family"] == "rank_weighted_visibility"
    ]
    assert len(visibility_claims) == 2
    assert {item["status"] for item in visibility_claims} == {"verified"}
    assert {item["entity"] for item in visibility_claims} == {
        "color=red + sleeve length=long sleeve",
        "color=pink + sleeve length=long sleeve",
    }
    assert payload["summary"]["mapping_issue_count"] == 0

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Both are narrower")
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["aggregation_rule_id"] == (
        "winning_summary_synthesis_v1"
    )


def test_validate_launch_report_pdf_checks_central_alpha_without_equals(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 1,
                "bundle_key": "finish=natural + spf=no spf",
                "gross_weight_share": 0.552758,
                "incremental_weight_share": 0.552758,
                "cumulative_weight_share": 0.552758,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "visibility-alpha",
                            "type": "body_text",
                            "text": (
                                "At central alpha 1.0; showing how retailer "
                                "filtering organizes category visibility."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "rank_weighted_visibility"
    )
    assert claim["status"] == "verified"
    assert claim["details"]["observed_values"] == {"alpha": 1.0}
    assert claim["details"]["package_values"] == {"available_alphas": [1.0]}


def test_validate_launch_report_pdf_checks_visibility_gross_suffix_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "blue + long sleeve",
                "count_top_seller": 9,
                "count_other": 15,
                "top_seller_base": 37,
                "other_base": 164,
                "pct_top_seller": 0.2432432432,
                "pct_other": 0.0914634146,
                "top_seller_brand_count": 8,
            }
        ],
    )
    _write_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 3,
                "bundle_key": "color=blue + sleeve_length=long sleeve",
                "gross_weight_share": 0.211,
                "incremental_weight_share": 0.0,
                "cumulative_weight_share": 0.734,
                "gross_sku_count": 21,
                "incremental_sku_count": 0,
            }
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "visibility-2",
                            "type": "table",
                            "table_model": {
                                "header_rows": 0,
                                "rows": [
                                    {
                                        "cells": [
                                            {
                                                "text": (
                                                    "blue + long sleeve | 21.1% Gross "
                                                    "| Not incremental | Broad; repetitive"
                                                )
                                            }
                                        ]
                                    }
                                ],
                            },
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert {item["claim_family"] for item in payload["claims"]} == {
        "rank_weighted_visibility"
    }
    claim = payload["claims"][0]
    assert claim["entity"] == "color=blue + sleeve_length=long sleeve"
    assert claim["details"]["observed_values"] == {"gross_weight_share_pct": 21.1}


def test_validate_launch_report_pdf_checks_visibility_candidate_shelf_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 1,
                "bundle_key": "lifestyle=contemporary + sleeve_length=long sleeve",
                "gross_weight_share": 0.302,
                "incremental_weight_share": 0.281,
                "cumulative_weight_share": 0.281,
            }
        ],
    )
    _write_csv(
        package_dir / "web_shelf_candidate_shelves.csv",
        [
            {
                "alpha": 1.0,
                "bundle_key": "color=black + sleeve length=long sleeve",
                "gross_weight_share": 0.171,
                "gross_sku_count": 13,
                "gross_brand_count": 10,
            }
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "visibility-candidate",
                            "type": "body_text",
                            "text": (
                                "black + long sleeve | 17.1% Gross | "
                                "Not incremental | Broad; brand-skewed"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "rank_weighted_visibility"
    )
    assert claim["status"] == "verified"
    assert claim["file"] == "web_shelf_candidate_shelves.csv"
    assert claim["entity"] == "color=black + sleeve length=long sleeve"
    assert claim["details"]["matched_row_keys"]["alpha"] == 1.0


def test_validate_launch_report_pdf_checks_visibility_common_component_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "web_shelf_candidate_shelves.csv",
        [
            {
                "alpha": 1.0,
                "bundle_key": "color=blue + sleeve length=long sleeve",
                "gross_weight_share": 0.211,
                "gross_sku_count": 20,
                "gross_brand_count": 12,
            },
            {
                "alpha": 1.0,
                "bundle_key": "color=black + sleeve length=long sleeve",
                "gross_weight_share": 0.171,
                "gross_sku_count": 16,
                "gross_brand_count": 10,
            },
            {
                "alpha": 1.0,
                "bundle_key": "color=brown + sleeve length=long sleeve",
                "gross_weight_share": 0.14,
                "gross_sku_count": 14,
                "gross_brand_count": 9,
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "visibility-summary",
                            "type": "body_text",
                            "text": (
                                "Rank-weighted visibility reveals that long sleeve "
                                "serves as the common category spine, with color "
                                "variants creating overlapping gross-visibility "
                                "pockets."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "rank_weighted_visibility"
    )
    assert claim["status"] == "verified"
    assert claim["file"] == "web_shelf_candidate_shelves.csv"
    assert claim["details"]["matched_row_keys"] == {
        "attribute_name": "sleeve length",
        "attribute_value": "long sleeve",
    }
    assert claim["details"]["aggregation_rule_id"] == (
        "visibility_common_component_spine_v1"
    )
    assert claim["details"]["package_values"]["supporting_row_count"] == 3


def test_validate_launch_report_pdf_checks_total_visibility_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Adult + Can",
                "count_top_seller": 20,
                "count_other": 30,
                "top_seller_base": 37,
                "other_base": 164,
                "pct_top_seller": 0.5405405405,
                "pct_other": 0.1829268293,
                "top_seller_brand_count": 12,
            }
        ],
    )
    _write_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 1,
                "bundle_key": "life_stage=adult + package_type=can",
                "gross_weight_share": 0.726,
                "incremental_weight_share": 0.726,
                "cumulative_weight_share": 0.726,
                "gross_sku_count": 90,
                "incremental_sku_count": 90,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "visibility-3",
                            "type": "text",
                            "text": (
                                '"Adult + Can" dominates total visibility (72.6%), '
                                "but functions strictly as a category baseline."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert {item["claim_family"] for item in payload["claims"]} == {
        "rank_weighted_visibility"
    }
    claim = payload["claims"][0]
    assert claim["entity"] == "life_stage=adult + package_type=can"
    assert claim["details"]["observed_values"] == {"gross_weight_share_pct": 72.6}


def test_validate_launch_report_pdf_checks_visibility_with_display_tolerance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "web_shelf_selected_shelves.csv",
        [
            {
                "alpha": 1.0,
                "shelf_rank": 2,
                "bundle_key": "form=pressed powder + spf=no spf",
                "gross_weight_share": 0.51829861570441,
                "incremental_weight_share": 0.3313179268379065,
                "cumulative_weight_share": 0.886199397539822,
                "gross_sku_count": 86,
                "incremental_sku_count": 64,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "visibility-4",
                            "type": "text",
                            "text": (
                                "Pressed Powder + No SPF: Gross Weight 51.6%; "
                                "Incremental Weight 33.0%; Structural Refinements "
                                "Brings cumulative selected weight to 88.3%."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["claim_family"] == "rank_weighted_visibility"
    assert claim["status"] == "verified"


def test_validate_launch_report_pdf_routes_sale_pressure_exposure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "garment type=cardigan + sleeve length=long sleeve",
                "bundle_label": "cardigan + long sleeve",
                "count_top_seller": 27,
                "count_other": 6,
                "top_seller_base": 96,
                "other_base": 482,
                "pct_top_seller": 0.28125,
                "pct_other": 0.0124481328,
                "top_seller_brand_count": 17,
            }
        ],
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "product_name": f"Sale Product {idx}",
                "garment type": "cardigan",
                "sleeve length": "long sleeve",
                "sale_pressure_status": "sale_pressure",
            }
            for idx in range(3)
        ]
        + [
            {
                "product_name": f"Clean Product {idx}",
                "garment type": "cardigan",
                "sleeve length": "long sleeve",
                "sale_pressure_status": "not_observed_sale_pressure",
            }
            for idx in range(24)
        ],
    )
    _write_csv(
        package_dir / "sale_pressure_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_label": "cardigan + long sleeve",
                "count_sale_pressure": 3,
                "count_not_observed_sale_pressure": 24,
                "sale_pressure_base": 27,
                "not_observed_sale_pressure_base": 24,
                "pct_sale_pressure": 0.1111111111,
                "pct_not_observed_sale_pressure": 0.8888888889,
                "sale_pressure_brand_count": 3,
                "prevalence_ratio": 0.13,
            }
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-pressure-1",
                            "type": "text",
                            "text": (
                                "cardigan + long sleeve: Sale-Pressure Exposure "
                                "11.1% exposed; Read Cleanest main bundle"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["entity"] == "cardigan + long sleeve"
    assert claim["file"] == "product_filter_matrix.csv"
    assert claim["details"]["package_values"]["sale_pressure_count"] == 3
    assert claim["details"]["package_values"]["product_count"] == 27


def test_validate_launch_report_pdf_verifies_qualitative_low_sale_pressure_exposure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low top sneakers",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "color=white + material=leather",
                "bundle_label": "white + leather",
                "count_top_seller": 10,
                "count_other": 4,
                "top_seller_base": 42,
                "other_base": 165,
                "pct_top_seller": 0.2380952381,
                "pct_other": 0.0242424242,
                "top_seller_brand_count": 8,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Sale Product",
                "color": "white",
                "material": "leather",
                "sale_pressure_status": "sale_pressure",
            }
        ]
        + [
            {
                "product_name": f"Clean Product {idx}",
                "color": "white",
                "material": "leather",
                "sale_pressure_status": "not_observed_sale_pressure",
            }
            for idx in range(9)
        ],
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-pressure-qualitative",
                            "type": "text",
                            "text": (
                                "Clean white-leather winners remain largely "
                                "unexposed to sale pressure."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["entity"] == "white + leather"
    assert claim["file"] == "top_seller_products.csv"
    assert (
        claim["details"]["observed_values"]["qualitative_low_sale_pressure_exposure"]
        is True
    )
    assert claim["details"]["package_values"]["sale_pressure_count"] == 1
    assert claim["details"]["package_values"]["product_count"] == 10
    assert claim["details"]["package_values"]["pct_sale_pressure_exposed"] == 10.0
    assert (
        claim["details"]["qualitative_threshold_policy"]["low_exposure_max_pct"] == 20.0
    )


def test_validate_launch_report_pdf_verifies_sale_pressure_exposure_comparison(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low top sneakers",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "color=white + material=leather",
                "bundle_label": "white + leather",
                "count_top_seller": 10,
                "count_other": 4,
                "top_seller_base": 42,
                "other_base": 165,
                "pct_top_seller": 0.2380952381,
                "pct_other": 0.0242424242,
                "top_seller_brand_count": 8,
            }
        ],
    )
    mesh_rows = [
        {
            "product_name": f"Mesh Sale Product {idx}",
            "material": "mesh",
            "color": "blue",
            "listing_status": "recent",
            "top_seller_status": "other",
            "sale_pressure_status": "sale_pressure",
        }
        for idx in range(4)
    ] + [
        {
            "product_name": f"Mesh Clean Product {idx}",
            "material": "mesh",
            "color": "blue",
            "listing_status": "recent",
            "top_seller_status": "other",
            "sale_pressure_status": "not_observed_sale_pressure",
        }
        for idx in range(6)
    ]
    white_leather_rows = [
        {
            "product_name": "White Leather Sale Product",
            "material": "leather",
            "color": "white",
            "listing_status": "rest",
            "top_seller_status": "top_seller",
            "sale_pressure_status": "sale_pressure",
        }
    ] + [
        {
            "product_name": f"White Leather Clean Product {idx}",
            "material": "leather",
            "color": "white",
            "listing_status": "rest",
            "top_seller_status": "top_seller",
            "sale_pressure_status": "not_observed_sale_pressure",
        }
        for idx in range(9)
    ]
    _write_csv(
        package_dir / "product_filter_matrix.csv", mesh_rows + white_leather_rows
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-pressure-comparison",
                            "type": "text",
                            "text": (
                                "Note: Recent high-visibility mesh innovations show "
                                "higher promotion exposure than the white-leather core."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["entity"] == "sale_pressure_exposure_comparison"
    assert claim["file"] == "product_filter_matrix.csv"
    package_values = claim["details"]["package_values"]
    assert package_values["left"]["label"] == "mesh"
    assert package_values["left"]["cohort"] == "recent"
    assert package_values["left"]["pct_sale_pressure_exposed"] == 40.0
    assert package_values["right"]["label"] == "white + leather"
    assert package_values["right"]["cohort"] == "top_seller"
    assert package_values["right"]["pct_sale_pressure_exposed"] == 10.0
    assert package_values["delta_pct_points"] == 30.0


def test_validate_launch_report_pdf_does_not_leak_sale_pressure_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "cardigan + long sleeve",
                "count_top_seller": 27,
                "count_other": 6,
                "top_seller_base": 96,
                "other_base": 482,
                "pct_top_seller": 0.28125,
                "pct_other": 0.0124481328,
                "top_seller_brand_count": 17,
            }
        ],
    )
    _write_csv(
        package_dir / "sale_pressure_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_label": "cardigan + long sleeve",
                "count_sale_pressure": 3,
                "count_not_observed_sale_pressure": 24,
                "sale_pressure_base": 27,
                "not_observed_sale_pressure_base": 24,
                "pct_sale_pressure": 0.1111111111,
                "pct_not_observed_sale_pressure": 0.8888888889,
                "sale_pressure_brand_count": 3,
                "prevalence_ratio": 0.13,
            }
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-heading",
                            "type": "heading",
                            "group_id": "sale-panel",
                            "text": "Sale-Pressure Exposure",
                        },
                        {
                            "block_id": "top-seller-row",
                            "type": "text",
                            "group_id": "sale-panel",
                            "text": (
                                "cardigan + long sleeve: Top-Seller Penetration "
                                "28.1%; Brand Breadth 17 brands"
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["verified_count"] == 1
    assert {item["claim_family"] for item in payload["claims"]} == {"bundle_metric"}
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["entity"] == "cardigan + long sleeve"


def test_validate_launch_report_pdf_checks_zero_sale_pressure_exposure_from_recent_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_key": "bundle-a",
                "bundle_label": "cable-knit + long sleeve",
                "count_recent": 5,
                "count_rest": 10,
                "recent_base": 39,
                "rest_base": 152,
                "pct_recent": 0.1282051282,
                "pct_rest": 0.0657894737,
            }
        ],
    )
    _write_csv(
        package_dir / "recent_products.csv",
        [
            {
                "product_name": f"Clean Product {idx}",
                "knit_detail": "cable-knit",
                "sleeve length": "long sleeve",
                "sale_pressure_status": "not_observed_sale_pressure",
            }
            for idx in range(5)
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-10",
                    "slide_number": 10,
                    "page_number": 10,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-pressure-2",
                            "type": "text",
                            "text": (
                                "cable-knit + long sleeve: 7.9% recent penetration. "
                                "Small but clean; zero sale-pressure exposure in recent items."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["file"] == "recent_products.csv"
    assert claim["details"]["package_values"]["sale_pressure_count"] == 0


def test_validate_launch_report_pdf_checks_sale_pressure_overlap_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "sale_pressure_overlap.csv",
        [
            {
                "comparison": "sale_pressure_vs_recent",
                "left_cohort": "sale_pressure",
                "right_cohort": "recent",
                "left_count": 96,
                "right_count": 39,
                "overlap_count": 8,
                "pct_left": 0.0833333333,
                "pct_right": 0.2051282051,
            },
            {
                "comparison": "sale_pressure_vs_top_seller",
                "left_cohort": "sale_pressure",
                "right_cohort": "top_seller",
                "left_count": 96,
                "right_count": 39,
                "overlap_count": 3,
                "pct_left": 0.03125,
                "pct_right": 0.0769230769,
            },
            {
                "comparison": "sale_pressure_vs_recent_top_seller",
                "left_cohort": "sale_pressure",
                "right_cohort": "recent_and_top_seller",
                "left_count": 96,
                "right_count": 26,
                "overlap_count": 3,
                "pct_left": 0.03125,
                "pct_right": 0.1153846154,
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-pressure-overlap",
                            "type": "text",
                            "text": (
                                "Sale-pressure overlaps roughly ~20% of top sellers "
                                "and recent products."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["file"] == "sale_pressure_overlap.csv"
    assert (
        "top_seller overlap percent mismatch: expected 7.7%"
        in claim["details"]["reasons"]
    )


def test_validate_launch_report_pdf_checks_cohort_unspecified_sale_pressure_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "sale_pressure_overlap.csv",
        [
            {
                "comparison": "sale_pressure_vs_recent",
                "left_cohort": "sale_pressure",
                "right_cohort": "recent",
                "left_count": 96,
                "right_count": 39,
                "overlap_count": 8,
                "pct_left": 0.0833333333,
                "pct_right": 0.2051282051,
            },
            {
                "comparison": "sale_pressure_vs_top_seller",
                "left_cohort": "sale_pressure",
                "right_cohort": "top_seller",
                "left_count": 96,
                "right_count": 39,
                "overlap_count": 3,
                "pct_left": 0.03125,
                "pct_right": 0.0769230769,
            },
            {
                "comparison": "sale_pressure_vs_recent_top_seller",
                "left_cohort": "sale_pressure",
                "right_cohort": "recent_and_top_seller",
                "left_count": 96,
                "right_count": 26,
                "overlap_count": 3,
                "pct_left": 0.03125,
                "pct_right": 0.1153846154,
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-pressure-overlap",
                            "type": "text",
                            "text": (
                                "Moderate overall (~20% overlap). Core winning "
                                "bundles remain mostly clean of sell pressure."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["file"] == "sale_pressure_overlap.csv"
    assert claim["details"]["matched_row_keys"]["comparisons"] == [
        "sale_pressure_vs_recent"
    ]


def test_validate_launch_report_pdf_checks_sale_pressure_absence_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
    )
    _write_csv(
        package_dir / "sale_pressure_overlap.csv",
        [
            {
                "comparison": "sale_pressure_vs_recent",
                "left_cohort": "sale_pressure",
                "right_cohort": "recent",
                "left_count": 0,
                "right_count": 633,
                "overlap_count": 0,
                "pct_left": None,
                "pct_right": 0.0,
            },
            {
                "comparison": "sale_pressure_vs_top_seller",
                "left_cohort": "sale_pressure",
                "right_cohort": "top_seller",
                "left_count": 0,
                "right_count": 633,
                "overlap_count": 0,
                "pct_left": None,
                "pct_right": 0.0,
            },
            {
                "comparison": "sale_pressure_vs_recent_top_seller",
                "left_cohort": "sale_pressure",
                "right_cohort": "recent_and_top_seller",
                "left_count": 0,
                "right_count": 16,
                "overlap_count": 0,
                "pct_left": None,
                "pct_right": 0.0,
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-10",
                    "slide_number": 10,
                    "page_number": 10,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "sale-pressure-absence",
                            "type": "text",
                            "text": (
                                "Neither the dominant layer nor the emerging layer "
                                "shows evidence of being driven by promotional "
                                "sale pressure."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["file"] == "sale_pressure_overlap.csv"
    assert claim["details"]["comparison_outcome"] == "pass"
    assert claim["details"]["matched_row_keys"]["comparisons"] == [
        "sale_pressure_vs_recent",
        "sale_pressure_vs_top_seller",
        "sale_pressure_vs_recent_top_seller",
    ]


def test_validate_launch_report_pdf_accepts_integer_rounded_semicolon_bundle_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "pink + pink",
                "count_top_seller": 41,
                "count_other": 118,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.9111111111,
                "pct_other": 0.6704545455,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Pink + Pink: Top Sellers 91% (41 of 45); " "Others 67%"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    assert payload["summary"]["contradicted_count"] == 0
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["file"] == "top_seller_pairs.csv"


def test_validate_launch_report_pdf_rejects_mixed_recent_and_top_seller_bundle_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "hydrating/moisturizing + high shine",
                "count_recent": 8,
                "count_rest": 14,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1777777778,
                "pct_rest": 0.0795454545,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "hydrating/moisturizing + high shine",
                "count_top_seller": 5,
                "count_other": 17,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.1111111111,
                "pct_other": 0.0965909091,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-13",
                    "slide_number": 13,
                    "page_number": 13,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Hydrating/Moisturizing + High Shine | "
                                "17.8% (Recent) | 11.1% (Top Sellers)"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["verified_count"] == 0
    assert payload["summary"]["contradicted_count"] == 0
    assert payload["summary"]["unresolved_count"] == 1
    claim = payload["unresolved"][0]
    assert claim["status"] == "unresolved"
    assert claim["claim_family"] == "bundle_metric"
    assert "incompatible source bases" in claim["details"]["message"]
    assert claim["details"]["parsed_cohort_labels"] == ["recent", "top_seller"]


def test_validate_launch_report_pdf_verifies_recent_bundle_absence_from_top_sellers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "hydrating/moisturizing + twist-up/retractable",
                "count_recent": 7,
                "count_rest": 10,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0568181818,
                "recent_brand_count": 7,
            }
        ],
    )
    _write_csv(package_dir / "top_seller_pairs.csv", [])
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-13",
                    "slide_number": 13,
                    "page_number": 13,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Hydrating/Moisturizing + Twist-up | "
                                "7 recent products across 7 brands | "
                                "Does not recur in top-seller bundles"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["status"] == "verified"
    assert claim["details"]["observed_values"]["cohort_counts"] == {"recent": 7}
    assert claim["details"]["zero_occurrence_check"][0]["cohort"] == "top_seller"
    assert claim["details"]["zero_occurrence_check"][0]["passed"] is True
    assert claim["details"]["zero_occurrence_check"][0]["matched_rows"] == []


def test_validate_launch_report_pdf_prefers_explicit_bundle_label_over_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "Salmon + Sensitive Digestion",
                "count_recent": 10,
                "count_rest": 14,
                "recent_base": 633,
                "rest_base": 2531,
                "pct_recent": 0.0157977883,
                "pct_rest": 0.0055314105,
                "recent_brand_count": 5,
                "prevalence_ratio": 2.856,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Sensitive Digestion + High-Protein",
                "count_top_seller": 6,
                "count_other": 18,
                "top_seller_base": 633,
                "other_base": 2531,
                "pct_top_seller": 0.009478673,
                "pct_other": 0.0071118135,
                "top_seller_brand_count": 3,
                "prevalence_ratio": 1.3328,
            }
        ],
    )
    text = (
        "Salmon + Sensitive Digestion: Evidence Ratio 2.91x; Brand Spread 4 "
        "brands; Read Small functional/protein signal"
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": text,
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "Salmon + Sensitive Digestion"
    assert claim["details"]["matched_row_keys"] == {
        "bundle_label": "Salmon + Sensitive Digestion"
    }
    assert claim["details"]["reasons"] == [
        "brand-count mismatch: expected 5",
        "ratio mismatch: expected 2.86x",
    ]


def test_validate_launch_report_pdf_keeps_numeric_clause_after_bundle_comma(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Chunks in Gravy + Indoor",
                "count_top_seller": 12,
                "count_other": 15,
                "top_seller_base": 633,
                "other_base": 2531,
                "pct_top_seller": 0.018957346,
                "pct_other": 0.0059265113,
                "top_seller_brand_count": 5,
                "prevalence_ratio": 3.1987,
            },
            {
                "bundle_label": "Chunks in Gravy + Indoor",
                "count_top_seller": 7,
                "count_other": 21,
                "top_seller_base": 633,
                "other_base": 2531,
                "pct_top_seller": 0.011058452,
                "pct_other": 0.008296128,
                "top_seller_brand_count": 3,
                "prevalence_ratio": 1.82,
            },
        ],
    )
    text = (
        "'Chunks in Gravy + Indoor' aligns directly with current gravy winners, "
        "achieving a 1.82x evidence ratio."
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": text,
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "Chunks in Gravy + Indoor"
    assert claim["details"]["package_values"]["prevalence_ratio"] == 1.82


def test_validate_launch_report_pdf_does_not_fuzz_explicit_grain_free_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "adult + With Grain",
                "count_top_seller": 194,
                "count_other": 762,
                "top_seller_base": 633,
                "other_base": 2531,
                "pct_top_seller": 0.3064770932,
                "pct_other": 0.301066772,
                "top_seller_brand_count": 44,
            },
            {
                "bundle_label": "adult + Gluten Free",
                "count_top_seller": 10,
                "count_other": 22,
                "top_seller_base": 633,
                "other_base": 2531,
                "pct_top_seller": 0.0157977883,
                "pct_other": 0.0086922165,
                "top_seller_brand_count": 6,
            },
        ],
    )
    text = (
        "Adult + Grain-Free: Signal Read False Signal; Visibility Metric "
        "30.8% of top sellers vs 30.6% of rest"
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": text,
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["verified_count"] == 0
    assert payload["summary"]["contradicted_count"] == 0
    assert payload["summary"]["unresolved_count"] == 1
    claim = payload["unresolved"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "Adult + Grain-Free"
    assert claim["details"]["message"] == "no matching package row found for label"


def test_validate_launch_report_pdf_computes_missing_bundle_from_product_matrix(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "parent_product_id": "top-1",
                "brand": "Brand A",
                "top_seller_status": "top_seller",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "Grain-Free",
            },
            {
                "parent_product_id": "top-2",
                "brand": "Brand B",
                "top_seller_status": "top_seller",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "With Grain",
            },
            {
                "parent_product_id": "other-1",
                "brand": "Brand C",
                "top_seller_status": "other",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "Grain-Free",
            },
            {
                "parent_product_id": "other-2",
                "brand": "Brand D",
                "top_seller_status": "other",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "With Grain",
            },
            {
                "parent_product_id": "other-3",
                "brand": "Brand E",
                "top_seller_status": "other",
                "listing_status": "rest",
                "lifestage": "Kitten",
                "special diet": "Grain-Free",
            },
            {
                "parent_product_id": "other-4",
                "brand": "Brand F",
                "top_seller_status": "other",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "Limited Ingredient",
            },
        ],
    )
    text = (
        "Adult + Grain-Free: Signal Read False Signal; Visibility Metric "
        "50.0% of top sellers vs 25.0% of rest"
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": text,
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "Adult + Grain-Free"
    assert claim["file"] == "top_seller_computed_bundle_from_product_filter_matrix.csv"
    assert claim["details"]["package_values"]["calculation_source"] == (
        "product_filter_matrix.csv"
    )
    assert claim["details"]["counts"] == {"top_seller": 1, "other": 1}
    assert claim["details"]["denominators"] == {"top_seller": 2, "other": 4}


def test_validate_launch_report_pdf_computes_brand_span_from_product_matrix(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "parent_product_id": "top-1",
                "brand": "Brand A",
                "top_seller_status": "top_seller",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "Grain-Free",
            },
            {
                "parent_product_id": "top-2",
                "brand": "Brand B",
                "top_seller_status": "top_seller",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "Grain-Free",
            },
            {
                "parent_product_id": "top-3",
                "brand": "Brand C",
                "top_seller_status": "top_seller",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "With Grain",
            },
            {
                "parent_product_id": "other-1",
                "brand": "Brand D",
                "top_seller_status": "other",
                "listing_status": "rest",
                "lifestage": "Adult",
                "special diet": "Grain-Free",
            },
        ],
    )
    text = (
        "• Adult + Grain-Free: Matched Products 2 Top Sellers; "
        "Brand Distribution 2 Brands"
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "heading-1",
                            "type": "group_label",
                            "text": "Trait Distribution",
                        },
                        {
                            "block_id": "bundle-1",
                            "parent_id": "heading-1",
                            "type": "bullet_item",
                            "items": [text],
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_brand_concentration"
    assert claim["entity"] == "Adult + Grain-Free"
    assert claim["file"] == "top_seller_computed_bundle_from_product_filter_matrix.csv"
    assert claim["details"]["observed_values"] == {
        "brand_span": 2,
        "bundle_count": 2,
    }
    assert claim["details"]["package_values"]["top_seller_brand_count"] == 2
    assert claim["details"]["package_values"]["count_top_seller"] == 2


def test_validate_launch_report_pdf_contradicts_false_bundle_absence_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    bundle_label = "hydrating/moisturizing + twist-up/retractable"
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": bundle_label,
                "count_recent": 7,
                "count_rest": 10,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0568181818,
                "recent_brand_count": 7,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": bundle_label,
                "count_top_seller": 3,
                "count_other": 8,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.0666666667,
                "pct_other": 0.0454545455,
                "top_seller_brand_count": 3,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-13",
                    "slide_number": 13,
                    "page_number": 13,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Hydrating/Moisturizing + Twist-up | "
                                "7 recent products across 7 brands | "
                                "Does not recur in top-seller bundles"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["claim_family"] == "bundle_metric"
    assert claim["details"]["zero_occurrence_check"][0]["passed"] is False
    assert (
        claim["details"]["zero_occurrence_check"][0]["matched_rows"][0][
            "occurrence_count"
        ]
        == 3
    )
    assert claim["details"]["reasons"] == [
        "top_seller absence failed: matching source row is non-zero"
    ]


def test_validate_launch_report_pdf_verifies_bundle_absence_with_duplicate_support_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "hydrating/moisturizing + twist-up/retractable",
                "count_recent": 7,
                "count_rest": 10,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0568181818,
                "recent_brand_count": 7,
            },
            {
                "bundle_label": "hydrating moisturizing + twist-up/retractable",
                "count_recent": 7,
                "count_rest": 10,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0568181818,
                "recent_brand_count": 7,
            },
        ],
    )
    _write_csv(package_dir / "top_seller_pairs.csv", [])
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-13",
                    "slide_number": 13,
                    "page_number": 13,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Hydrating/Moisturizing + Twist-up | "
                                "7 recent products across 7 brands | "
                                "Does not recur in top-seller bundles"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "hydrating/moisturizing + twist-up/retractable"
    assert claim["details"]["observed_values"]["cohort_counts"] == {"recent": 7}
    assert claim["details"]["zero_occurrence_check"][0]["cohort"] == "top_seller"
    assert claim["details"]["zero_occurrence_check"][0]["passed"] is True


def test_validate_launch_report_pdf_verifies_bundle_brand_concentration_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "beige + pink",
                "count_top_seller": 17,
                "count_other": 9,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.3777777778,
                "pct_other": 0.0511363636,
                "top_seller_brand_count": 17,
                "top_seller_dominant_brand": "BRAND ALPHA",
                "top_seller_dominant_brand_count": 4,
                "top_seller_dominant_brand_share": 0.24,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "table-1",
                            "type": "table",
                            "table_model": {
                                "header_rows": 0,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Beige + Pink"},
                                            {"text": "Spans 17 brands"},
                                            {"text": "BRAND ALPHA accounts for 24%"},
                                        ]
                                    }
                                ],
                            },
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_brand_concentration"
    assert claim["entity"] == "beige + pink"
    assert claim["file"] == "top_seller_pairs.csv"
    assert claim["details"]["brand_span"] == 17
    assert claim["details"]["dominant_brand_name"] == "BRAND ALPHA"
    assert claim["details"]["dominant_brand_count"] == 4
    assert claim["details"]["dominant_brand_share"] == 24.0
    assert claim["details"]["comparison_outcome"] == "pass"
    assert claim["details"]["non_collapse"] is True


def test_validate_launch_report_pdf_contradicts_bad_bundle_brand_concentration_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "beige + pink",
                "count_top_seller": 17,
                "count_other": 9,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.3777777778,
                "pct_other": 0.0511363636,
                "top_seller_brand_count": 17,
                "top_seller_dominant_brand": "BRAND ALPHA",
                "top_seller_dominant_brand_count": 4,
                "top_seller_dominant_brand_share": 0.24,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "table-1",
                            "type": "table",
                            "table_model": {
                                "header_rows": 0,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Beige + Pink"},
                                            {"text": "Spans 17 brands"},
                                            {"text": "BRAND ALPHA accounts for 31%"},
                                        ]
                                    }
                                ],
                            },
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "bundle_brand_concentration"
    assert claim["details"]["reasons"] == [
        "dominant-brand share mismatch: expected 24.0%"
    ]


def test_validate_launch_report_pdf_verifies_bundle_brand_concentration_summaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "beige + pink",
                "count_top_seller": 17,
                "count_other": 9,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.3777777778,
                "pct_other": 0.0511363636,
                "top_seller_brand_count": 17,
                "top_seller_dominant_brand": "BRAND ALPHA",
                "top_seller_dominant_brand_count": 4,
                "top_seller_dominant_brand_share": 0.24,
            },
            {
                "bundle_label": "pink + red + long-wear",
                "count_top_seller": 10,
                "count_other": 4,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.2222222222,
                "pct_other": 0.0227272727,
                "top_seller_brand_count": 16,
                "top_seller_dominant_brand": "BRAND ALPHA",
                "top_seller_dominant_brand_count": 3,
                "top_seller_dominant_brand_share": 0.30,
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "BRAND ALPHA",
                "catalog_share": 0.0841584158,
                "top_seller_share_of_cohort": 0.2093023256,
                "over_index_vs_catalog_share": 2.4870041040,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-1",
                            "type": "text",
                            "text": (
                                "The top-seller cohort exhibits real brand "
                                "concentration, with BRAND ALPHA holding 9 of 45 "
                                "products (2.49x over-index)."
                            ),
                        },
                        {
                            "block_id": "body-1",
                            "type": "body_text",
                            "text": (
                                "However, the main winning bundles survive "
                                "contact with this concentration; BRAND ALPHA provides "
                                "amplitude, but not the direction itself."
                            ),
                        },
                        {
                            "block_id": "banner-1",
                            "type": "implication_banner",
                            "text": (
                                "No major winning-now bundle collapses into a "
                                "single-brand artifact upon inspection."
                            ),
                        },
                        {
                            "block_id": "table-title-1",
                            "type": "table_title",
                            "text": "Brand Breadth of Winning Bundles",
                            "groupId": "table-1",
                            "parentId": "table-1",
                        },
                        {
                            "block_id": "table-1",
                            "type": "table",
                            "groupId": "table-1",
                            "table_model": {
                                "header_rows": 0,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Beige + Pink"},
                                            {"text": "Spans 17 brands"},
                                            {"text": "BRAND ALPHA accounts for 24%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Pink + Red + Long-wear"},
                                            {"text": "Spans 16 brands"},
                                            {"text": "BRAND ALPHA accounts for 30%"},
                                        ]
                                    },
                                ],
                            },
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    families = [item["claim_family"] for item in payload["claims"]]
    assert families.count("bundle_brand_concentration") == 4
    summary_claims = [
        item
        for item in payload["claims"]
        if item["claim_family"] == "bundle_brand_concentration"
        and item["source_kind"] == "block_text"
    ]
    assert len(summary_claims) == 2
    for claim in summary_claims:
        assert claim["status"] == "verified"
        assert claim["details"]["comparison_outcome"] == "pass"
        assert claim["details"]["row_support"]
    amplitude_claim = next(
        item for item in summary_claims if "provides amplitude" in item["claim_text"]
    )
    assert amplitude_claim["details"]["brand_support"][0]["brand_name"] == "BRAND ALPHA"


def test_validate_launch_report_pdf_verifies_contextual_single_brand_concentration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Chunks in Gravy + Indoor",
                "count_top_seller": 8,
                "top_seller_base": 40,
                "count_other": 4,
                "other_base": 40,
                "pct_top_seller": 0.2,
                "pct_other": 0.1,
                "prevalence_ratio": 2.0,
                "top_seller_brand_count": 2,
            }
        ],
    )
    _write_csv(
        package_dir / "bundle_review_validation.csv",
        [
            {
                "bundle_label": "Chunks in Gravy + Indoor",
                "product_name": f"Pet Brand Beta Product {index}",
                "brand": "Pet Brand Beta",
            }
            for index in range(4)
        ]
        + [
            {
                "bundle_label": "Chunks in Gravy + Indoor",
                "product_name": "Pet Brand Delta Product",
                "brand": "Pet Brand Delta",
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "bullet_item",
                            "text": (
                                "'Chunks in Gravy + Indoor' aligns directly "
                                "with current gravy winners, achieving a 2.00x "
                                "evidence ratio."
                            ),
                        },
                        {
                            "block_id": "brand-1",
                            "type": "bullet_item",
                            "text": (
                                "Because this signal is 80% concentrated within "
                                "a single brand, it functions more as a line "
                                "extension than a broad category innovation."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    concentration_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "bundle_brand_concentration"
    )
    assert concentration_claim["status"] == "verified"
    assert concentration_claim["entity"] == "Chunks in Gravy + Indoor"
    assert concentration_claim["details"]["source_file"] == (
        "bundle_review_validation.csv"
    )
    assert (
        concentration_claim["details"]["package_values"]["dominant_brand_share"] == 80.0
    )
    assert concentration_claim["details"]["context_claim"]["claim_family"] == (
        "bundle_metric"
    )


def test_validate_launch_report_pdf_checks_adjacent_bundle_overindex_descriptor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Full + Matte + Pressed powder",
                "bundle_size": 3,
                "count_top_seller": 4,
                "top_seller_base": 40,
                "count_other": 4,
                "other_base": 80,
                "pct_top_seller": 0.1,
                "pct_other": 0.05,
                "prevalence_ratio": 2.0,
            },
            {
                "bundle_label": "Full + Natural + Blurring",
                "bundle_size": 3,
                "count_top_seller": 6,
                "top_seller_base": 40,
                "count_other": 2,
                "other_base": 80,
                "pct_top_seller": 0.15,
                "pct_other": 0.025,
                "prevalence_ratio": 6.0,
            },
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "label-1",
                            "type": "bullet_item",
                            "text": "Full + Matte + Pressed Powder",
                        },
                        {
                            "block_id": "descriptor-1",
                            "type": "bullet_item",
                            "text": "The sharpest top-seller over-index currently.",
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "bundle_metric"
        and item["claim_text"].startswith("The sharpest")
    )
    assert claim["status"] == "contradicted"
    assert claim["entity"] == "Full + Matte + Pressed powder"
    assert claim["details"]["aggregation_rule_id"] == (
        "adjacent_bundle_top_seller_overindex_rank_v1"
    )
    assert claim["details"]["package_values"]["prevalence_ratio_rank"] == 2
    assert claim["details"]["package_values"]["top_bundle_label"] == (
        "Full + Natural + Blurring"
    )


def test_validate_launch_report_pdf_checks_numeric_signal_references(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Buildable + Luminous + Pressed powder",
                "bundle_size": 3,
                "count_top_seller": 2,
                "top_seller_base": 45,
                "count_other": 3,
                "other_base": 90,
                "pct_top_seller": 0.0444444444,
                "pct_other": 0.0333333333,
                "prevalence_ratio": 1.3333333333,
            }
        ],
    )
    _write_csv(
        package_dir / "innovation_triples.csv",
        [
            {
                "bundle_label": "Buildable + Luminous + Pressed powder",
                "bundle_size": 3,
                "count_recent": 6,
                "recent_base": 68,
                "count_rest": 6,
                "rest_base": 271,
                "pct_recent": 0.0882352941,
                "pct_rest": 0.0221402214,
                "prevalence_ratio": 3.9852941176,
            }
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "top-seller-claim",
                            "type": "body_text",
                            "text": (
                                "Buildable + Luminous + Pressed powder: "
                                "Prevalence vs others 19.6% vs 14.0% (1.40x)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "recent-claim",
                            "type": "body_text",
                            "text": (
                                "Buildable + Luminous + Pressed powder: "
                                "Recent vs Rest Prevalence 27.7% vs 12.2% (2.27x)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bridge-claim",
                            "type": "body_text",
                            "text": (
                                "The most credible bridge between current winners "
                                "(19.6% vs 14.0%) and emerging releases "
                                "(27.7% vs 12.2%)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                },
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    bridge_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("The most credible bridge")
    )
    assert bridge_claim["status"] == "contradicted"
    assert bridge_claim["claim_family"] == "summary_synthesis"
    assert bridge_claim["details"]["aggregation_rule_id"] == (
        "deck_numeric_signal_reference_v1"
    )
    assert len(bridge_claim["details"]["support_claims"]) == 2
    assert bridge_claim["details"]["comparison_outcome"] == "fail"


def test_validate_launch_report_pdf_verifies_multi_brand_movement_summary_from_bundle_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "red + high shine",
                "count_recent": 11,
                "count_rest": 20,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.2444444444,
                "pct_rest": 0.1136363636,
                "recent_brand_count": 9,
                "rest_brand_count": 17,
            },
            {
                "bundle_label": "wine + stick",
                "count_recent": 11,
                "count_rest": 22,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.2444444444,
                "pct_rest": 0.125,
                "recent_brand_count": 6,
                "rest_brand_count": 16,
            },
            {
                "bundle_label": "wine + high shine",
                "count_recent": 7,
                "count_rest": 7,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0397727273,
                "recent_brand_count": 5,
                "rest_brand_count": 7,
            },
        ],
    )
    _write_csv(
        package_dir / "innovation_triples.csv",
        [
            {
                "bundle_label": "purple + wine + stick",
                "count_recent": 9,
                "count_rest": 11,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.2,
                "pct_rest": 0.0625,
                "recent_brand_count": 6,
                "rest_brand_count": 10,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-1",
                            "type": "title",
                            "text": "Emerging Signal 1: Wine and High-Shine Sticks",
                        },
                        {
                            "block_id": "summary-1",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "This is a multi-brand movement spanning 5 to 9 "
                                    "brands depending on the specific attribute bundle."
                                )
                            ],
                        },
                        {
                            "block_id": "table-1",
                            "type": "table",
                            "table_model": {
                                "header_rows": 1,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Attribute Bundle"},
                                            {"text": "Recent (%)"},
                                            {"text": "Rest (%)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Red + High Shine"},
                                            {"text": "24% (11 products)"},
                                            {"text": "11% (Rest)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Wine + Stick"},
                                            {"text": "24% (11 products)"},
                                            {"text": "13% (Rest)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Purple + Wine + Stick"},
                                            {"text": "20% (9 products)"},
                                            {"text": "6% (Rest)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Wine + High Shine"},
                                            {"text": "16% (7 products)"},
                                            {"text": "4% (Rest)"},
                                        ]
                                    },
                                ],
                            },
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "bundle_brand_concentration"
        and "multi-brand movement" in item["claim_text"]
    )
    assert summary_claim["status"] == "verified"
    assert summary_claim["details"]["comparison_outcome"] == "pass"
    assert summary_claim["details"]["brand_span_range"] == {
        "minimum": 5,
        "maximum": 9,
    }
    assert [
        support["claim_text"] for support in summary_claim["details"]["row_support"]
    ] == [
        "red + high shine",
        "wine + stick",
        "purple + wine + stick",
        "wine + high shine",
    ]
    assert [
        support["brand_span"] for support in summary_claim["details"]["row_support"]
    ] == [
        9,
        6,
        6,
        5,
    ]


def test_validate_launch_report_pdf_verifies_emerging_lane_profile_bullets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "red + high shine",
                "count_recent": 11,
                "count_rest": 20,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.2444444444,
                "pct_rest": 0.1136363636,
                "recent_brand_count": 9,
                "rest_brand_count": 17,
            },
            {
                "bundle_label": "wine + stick",
                "count_recent": 11,
                "count_rest": 22,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.2444444444,
                "pct_rest": 0.125,
                "recent_brand_count": 6,
                "rest_brand_count": 16,
            },
            {
                "bundle_label": "wine + high shine",
                "count_recent": 7,
                "count_rest": 7,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0397727273,
                "recent_brand_count": 5,
                "rest_brand_count": 7,
            },
            {
                "bundle_label": "buildable coverage + long-wear",
                "count_recent": 7,
                "count_rest": 12,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0681818182,
                "recent_brand_count": 5,
                "rest_brand_count": 9,
            },
            {
                "bundle_label": "buildable coverage + matte",
                "count_recent": 7,
                "count_rest": 12,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0681818182,
                "recent_brand_count": 6,
                "rest_brand_count": 10,
            },
        ],
    )
    _write_csv(
        package_dir / "innovation_triples.csv",
        [
            {
                "bundle_label": "purple + wine + stick",
                "count_recent": 9,
                "count_rest": 11,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.2,
                "pct_rest": 0.0625,
                "recent_brand_count": 6,
                "rest_brand_count": 10,
            }
        ],
    )
    _write_csv(
        package_dir / "mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "benefits",
                "attribute_value": "hydrating/moisturizing",
                "count_recent": 22,
                "count_rest": 83,
                "recent_base": 36,
                "rest_base": 162,
                "pct_recent": 0.6111111111,
                "pct_rest": 0.5123456790,
                "delta": 0.0987654321,
            },
            {
                "attribute_name": "benefits",
                "attribute_value": "smoothing/blur",
                "count_recent": 2,
                "count_rest": 7,
                "recent_base": 36,
                "rest_base": 162,
                "pct_recent": 0.0555555556,
                "pct_rest": 0.0432098765,
                "delta": 0.0123456791,
            },
        ],
    )
    _write_csv(
        package_dir / "resolved_core_comparison.csv",
        [
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "buildable coverage",
                "count_recent": 11,
                "count_rest": 19,
                "recent_base": 31,
                "rest_base": 152,
                "pct_recent": 0.3548387097,
                "pct_rest": 0.125,
                "delta": 0.2298387097,
            },
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "full coverage",
                "count_recent": 14,
                "count_rest": 87,
                "recent_base": 31,
                "rest_base": 152,
                "pct_recent": 0.4516129032,
                "pct_rest": 0.5723684211,
                "delta": -0.1207555179,
            },
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-0",
                            "type": "title",
                            "text": "Analytical Recap",
                        },
                        {
                            "block_id": "summary-0",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "Emerging signal: Recent launches introduce two "
                                    "modest lanes: wine/red high-shine sticks and "
                                    "buildable blurred long-wear formulas."
                                ),
                            ],
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-1",
                            "type": "title",
                            "text": "Emerging Signal 1: Wine and High-Shine Sticks",
                        },
                        {
                            "block_id": "summary-1",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "The innovation layer reveals a modest emerging signal "
                                    "splitting into two adjacent lanes rather than a "
                                    "category reset."
                                ),
                                (
                                    "The first lane centers on wine-red high-shine sticks "
                                    "accompanied by stronger care language."
                                ),
                            ],
                        },
                        {
                            "block_id": "table-1",
                            "type": "table",
                            "table_model": {
                                "header_rows": 1,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Attribute Bundle"},
                                            {"text": "Recent (%)"},
                                            {"text": "Rest (%)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Red + High Shine"},
                                            {"text": "24% (11 products)"},
                                            {"text": "11% (Rest)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Wine + Stick"},
                                            {"text": "24% (11 products)"},
                                            {"text": "13% (Rest)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Purple + Wine + Stick"},
                                            {"text": "20% (9 products)"},
                                            {"text": "6% (Rest)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Wine + High Shine"},
                                            {"text": "16% (7 products)"},
                                            {"text": "4% (Rest)"},
                                        ]
                                    },
                                ],
                            },
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-2",
                            "type": "title",
                            "text": "Signal 2: Buildable and Blurred Coverage Emerging",
                        },
                        {
                            "block_id": "summary-2",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "The second innovation lane moves away from rigid "
                                    "full coverage toward buildable, blurred, "
                                    "softer-performance formulas."
                                ),
                                (
                                    "This line successfully maintains performance claims "
                                    "(long-wear, matte) while introducing soft-focus, "
                                    "lower-drag wear states."
                                ),
                            ],
                        },
                        {
                            "block_id": "table-2",
                            "type": "table",
                            "table_model": {
                                "header_rows": 1,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Attribute Bundle"},
                                            {"text": "Recent (%)"},
                                            {"text": "Rest (%)"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Buildable Coverage (Base)"},
                                            {"text": "35.5%"},
                                            {"text": "12.5%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Buildable Coverage + Long-wear"},
                                            {"text": "16%"},
                                            {"text": "7%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Buildable Coverage + Matte"},
                                            {"text": "16%"},
                                            {"text": "7%"},
                                        ]
                                    },
                                ],
                            },
                        },
                    ],
                    "figure_regions": [],
                },
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    first_lane_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "emerging_lane_summary"
        and "first lane centers on" in item["claim_text"]
    )
    assert first_lane_claim["status"] == "verified"
    assert first_lane_claim["details"]["comparison_outcome"] == "pass"
    assert "red + high shine" in first_lane_claim["details"]["component_entities"]
    assert "wine + stick" in first_lane_claim["details"]["component_entities"]
    assert [
        item["concept"] for item in first_lane_claim["details"]["attribute_support"]
    ] == ["care_language"]

    second_lane_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "emerging_lane_summary"
        and "second innovation lane moves away" in item["claim_text"]
    )
    assert second_lane_claim["status"] == "verified"
    assert second_lane_claim["details"]["comparison_outcome"] == "pass"
    assert {
        item["concept"] for item in second_lane_claim["details"]["attribute_support"]
    } == {"away_from_baseline", "blurred_states"}
    assert "buildable coverage" in second_lane_claim["details"]["component_entities"]

    line_extension_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "emerging_lane_summary"
        and "This line successfully maintains" in item["claim_text"]
    )
    assert line_extension_claim["status"] == "verified"
    assert line_extension_claim["details"]["comparison_outcome"] == "pass"
    assert {
        item["entity"] for item in line_extension_claim["details"]["row_support"]
    } == {
        "buildable coverage + long-wear",
        "buildable coverage + matte",
    }

    adjacent_lanes_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "emerging_lane_summary"
        and "adjacent lanes" in item["claim_text"]
    )
    assert adjacent_lanes_claim["status"] == "verified"
    assert adjacent_lanes_claim["details"]["comparison_outcome"] == "pass"
    assert adjacent_lanes_claim["details"]["aggregation_rule_id"] == (
        "emerging_lane_count_v1"
    )
    assert adjacent_lanes_claim["details"]["expected_lane_count"] == 2
    assert adjacent_lanes_claim["details"]["observed_lane_count"] == 2
    assert {
        item["aggregation_rule_id"]
        for item in adjacent_lanes_claim["details"]["component_claims"]
    } == {
        "emerging_lane_profile_v1",
        "emerging_lane_shift_v1",
    }

    recap_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "emerging_lane_summary"
        and item["claim_text"].startswith("Emerging signal: Recent launches introduce")
    )
    assert recap_claim["status"] == "verified"
    assert recap_claim["details"]["comparison_outcome"] == "pass"
    assert recap_claim["details"]["aggregation_rule_id"] == "emerging_lane_recap_v1"
    assert recap_claim["details"]["expected_lane_count"] == 2
    assert recap_claim["details"]["observed_lane_count"] == 2
    assert [
        item["matched_slide_number"]
        for item in recap_claim["details"]["descriptor_support"]
    ] == [9, 11]


def test_validate_launch_report_pdf_verifies_overall_attribute_share_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "benefits",
                "attribute_value": "hydrating/moisturizing",
                "count_top_seller": 14,
                "count_other": 91,
                "top_seller_base": 43,
                "other_base": 155,
                "pct_top_seller": 0.3255813953,
                "pct_other": 0.5870967742,
                "delta": -0.2615153789,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-13",
                    "slide_number": 13,
                    "page_number": 13,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "table-1",
                            "type": "table",
                            "table_model": {
                                "rows": [
                                    {
                                        "cells": [
                                            {
                                                "text": "Explicit Hydrating Language (Overall)"
                                            },
                                            {"text": "58.7% (Others)"},
                                            {"text": "32.6% (Top Sellers)"},
                                        ]
                                    }
                                ]
                            },
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "attribute_share"
    assert claim["entity"] == "hydrating/moisturizing"
    assert claim["file"] == "top_seller_mapped_attribute_comparison.csv"
    assert claim["details"]["rank_basis_or_share_basis"] == "top_seller_vs_other"
    assert claim["details"]["expected_numeric_values"] == {
        "top_seller": 32.55813953,
        "other": 58.70967742,
    }
    assert claim["details"]["denominators"] == {
        "top_seller": 43,
        "other": 155,
    }


def test_validate_launch_report_pdf_routes_prose_percent_comparisons_to_attribute_share(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "resolved_core_comparison.csv",
        [
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "Buildable",
                "count_recent": 37,
                "count_rest": 83,
                "recent_base": 67,
                "rest_base": 266,
                "pct_recent": 0.552238806,
                "pct_rest": 0.3120300752,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "skin benefits",
                "attribute_value": "Blurring",
                "count_top_seller": 18,
                "count_other": 48,
                "top_seller_base": 54,
                "other_base": 210,
                "pct_top_seller": 0.3333333333,
                "pct_other": 0.2285714286,
            }
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "buildable-1",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "Buildable appears in 55.2% of recent products "
                                    "versus 31.2% in the rest of the catalog."
                                )
                            ],
                        },
                        {
                            "block_id": "blurring-1",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "Blurring over-indexes among top sellers at "
                                    "33.3% vs 22.9% for other products."
                                )
                            ],
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 2
    assert {claim["claim_family"] for claim in payload["claims"]} == {"attribute_share"}
    assert {claim["entity"] for claim in payload["claims"]} == {
        "Buildable",
        "Blurring",
    }
    assert all(
        claim["details"]["rank_basis_or_share_basis"]
        in {"recent_vs_rest", "top_seller_vs_other"}
        for claim in payload["claims"]
    )
    blurring_claim = next(
        claim for claim in payload["claims"] if claim["entity"] == "Blurring"
    )
    assert blurring_claim["details"]["matched_metrics"] == [
        "top_seller_percent",
        "other_percent",
    ]
    for claim in payload["claims"]:
        candidate_evaluations = claim["details"]["candidate_evaluations"]
        assert candidate_evaluations[0]["selected_candidate"] is True
        assert (
            candidate_evaluations[0]["matched_row_keys"]
            == claim["details"]["matched_row_keys"]
        )


def test_validate_launch_report_pdf_prefers_attribute_share_candidate_matching_text_cohort(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "form_children",
                "attribute_value": "pressed powder",
                "count_top_seller": 2,
                "count_other": 4,
                "top_seller_base": 11,
                "other_base": 51,
                "pct_top_seller": 0.1818181818,
                "pct_other": 0.0784313725,
            }
        ],
    )
    _write_csv(
        package_dir / "resolved_core_comparison.csv",
        [
            {
                "attribute_name": "resolved_form",
                "attribute_value": "pressed powder",
                "count_recent": 15,
                "count_rest": 65,
                "recent_base": 36,
                "rest_base": 142,
                "pct_recent": 0.4166666667,
                "pct_rest": 0.4577464789,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-6",
                    "slide_number": 6,
                    "page_number": 6,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "attribute-share-1",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "Buildable pressed powder appears in 16.2% "
                                    "of recent vs 6.2% of rest."
                                )
                            ],
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item for item in payload["claims"] if item["claim_family"] == "attribute_share"
    )
    assert claim["status"] == "contradicted"
    assert claim["file"] == "resolved_core_comparison.csv"
    assert claim["details"]["matched_row_keys"] == {
        "attribute_name": "resolved_form",
        "attribute_value": "pressed powder",
    }
    assert claim["details"]["rank_basis_or_share_basis"] == "recent_vs_rest"
    assert "recent_percent" in claim["details"]["mismatched_metrics"]


def test_validate_launch_report_pdf_resolves_remaining_page2_summary_families(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "pink + pink",
                "count_top_seller": 41,
                "count_other": 118,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.9111111111,
                "pct_other": 0.6704545455,
            },
            {
                "bundle_label": "brown + brown",
                "count_top_seller": 36,
                "count_other": 84,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.8,
                "pct_other": 0.4772727273,
            },
            {
                "bundle_label": "beige + pink",
                "count_top_seller": 34,
                "count_other": 69,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.7555555556,
                "pct_other": 0.3920454545,
                "top_seller_brand_count": 17,
                "top_seller_dominant_brand": "BRAND ALPHA",
                "top_seller_dominant_brand_count": 4,
                "top_seller_dominant_brand_share": 0.24,
            },
            {
                "bundle_label": "beige + red",
                "count_top_seller": 31,
                "count_other": 53,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.6888888889,
                "pct_other": 0.3011363636,
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "pink + red + long-wear",
                "count_top_seller": 27,
                "count_other": 51,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.6,
                "pct_other": 0.2897727273,
                "top_seller_brand_count": 16,
                "top_seller_dominant_brand": "BRAND ALPHA",
                "top_seller_dominant_brand_count": 8,
                "top_seller_dominant_brand_share": 0.2962962963,
            },
            {
                "bundle_label": "beige + pink + long-wear",
                "count_top_seller": 24,
                "count_other": 40,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.5333333333,
                "pct_other": 0.2272727273,
            },
            {
                "bundle_label": "pink + red + full coverage",
                "count_top_seller": 23,
                "count_other": 40,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.5111111111,
                "pct_other": 0.2272727273,
            },
            {
                "bundle_label": "full coverage + liquid + long-wear",
                "count_top_seller": 11,
                "count_other": 12,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.2444444444,
                "pct_other": 0.0681818182,
                "top_seller_brand_count": 10,
                "top_seller_dominant_brand_count": 2,
            },
        ],
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "hydrating/moisturizing + twist-up/retractable",
                "count_recent": 7,
                "count_rest": 0,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0,
                "recent_brand_count": 7,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "shade",
                "attribute_value": "pink",
                "count_top_seller": 36,
                "count_other": 121,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.8,
                "pct_other": 0.6875,
                "delta": 0.1125,
            },
            {
                "attribute_name": "shade",
                "attribute_value": "red",
                "count_top_seller": 33,
                "count_other": 108,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.7333333333,
                "pct_other": 0.6136363636,
                "delta": 0.1196969697,
            },
            {
                "attribute_name": "shade",
                "attribute_value": "brown",
                "count_top_seller": 31,
                "count_other": 106,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.6888888889,
                "pct_other": 0.6022727273,
                "delta": 0.0866161616,
            },
            {
                "attribute_name": "form",
                "attribute_value": "stick form",
                "count_top_seller": 35,
                "count_other": 120,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.7777777778,
                "pct_other": 0.6818181818,
                "delta": 0.095959596,
            },
            {
                "attribute_name": "finish",
                "attribute_value": "matte finish",
                "count_top_seller": 30,
                "count_other": 112,
                "top_seller_base": 45,
                "other_base": 176,
                "pct_top_seller": 0.6666666667,
                "pct_other": 0.6363636364,
                "delta": 0.0303030303,
            },
            {
                "attribute_name": "benefits",
                "attribute_value": "hydrating/moisturizing",
                "count_top_seller": 14,
                "count_other": 91,
                "top_seller_base": 43,
                "other_base": 155,
                "pct_top_seller": 0.3255813953,
                "pct_other": 0.5870967742,
                "delta": -0.2615153789,
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_review_validation.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "color=beige + color=pink",
                "bundle_label": "beige + pink",
                "product_name": "Brand Alpha Silky Matte",
                "brand": "BRAND ALPHA",
                "parent_product_id": "brand-alpha-1",
                "pareto_rank": 2,
                "pareto_bucket": "A",
                "sales_share": 0.2,
                "rating": 4.7,
                "review_count": 500,
                "reviews_positive_headline": "Smooth comfortable wear",
                "reviews_positive_comment": (
                    "The formula feels smooth, comfortable, and pigment rich."
                ),
                "reviews_negative_headline": "Shade inconsistency",
                "reviews_negative_comment": (
                    "The shade can vary and the formula consistency is uneven."
                ),
                "review_1_headline": "",
                "review_1_comment": "",
                "review_1_rating": None,
                "review_1_created_date": "",
                "review_2_headline": "",
                "review_2_comment": "",
                "review_2_rating": None,
                "review_2_created_date": "",
                "review_3_headline": "",
                "review_3_comment": "",
                "review_3_rating": None,
                "review_3_created_date": "",
            },
            {
                "bundle_size": 3,
                "bundle_key": "color=pink + color=red + wear_claims=long_wear",
                "bundle_label": "pink + red + long-wear",
                "product_name": "Brand Alpha Sleek Satin",
                "brand": "BRAND ALPHA",
                "parent_product_id": "brand-alpha-2",
                "pareto_rank": 3,
                "pareto_bucket": "A",
                "sales_share": 0.18,
                "rating": 4.6,
                "review_count": 420,
                "reviews_positive_headline": "Great texture and glide",
                "reviews_positive_comment": (
                    "It glides on easily with smooth texture and comfortable wear."
                ),
                "reviews_negative_headline": "Formula consistency issue",
                "reviews_negative_comment": (
                    "The formula can feel inconsistent and the shade payoff shifts."
                ),
                "review_1_headline": "",
                "review_1_comment": "",
                "review_1_rating": None,
                "review_1_created_date": "",
                "review_2_headline": "",
                "review_2_comment": "",
                "review_2_rating": None,
                "review_2_created_date": "",
                "review_3_headline": "",
                "review_3_comment": "",
                "review_3_rating": None,
                "review_3_created_date": "",
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "BRAND ALPHA",
                "catalog_share": 0.0841584158,
                "top_seller_share_of_cohort": 0.2093023256,
                "over_index_vs_catalog_share": 2.4870041040,
            }
        ],
    )

    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-2",
                            "type": "title",
                            "text": "Analytical Recap",
                        },
                        {
                            "block_id": "summary-2a",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "Winning now: The category is anchored by broad "
                                    "beige/pink/red/brown shade ranges, with long-wear "
                                    "and full coverage as the definitive performance "
                                    "overlays. Validation: These winner signals survive "
                                    "brand concentration (e. g., BRAND ALPHA) and are corroborated "
                                    "by PDP review data."
                                ),
                                (
                                    "The divergence: The primary difference between current "
                                    "winners and recent launches is the stronger, more "
                                    "explicit pairing of hydration language with "
                                    "retractable-stick packaging."
                                ),
                                (
                                    "Constants: Pink, red, brown, stick form, and matte "
                                    "finish remain stable categories with weak "
                                    "discriminatory power."
                                ),
                            ],
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-4",
                            "type": "title",
                            "text": "The Winning Architecture: Mainstream Shade Bundles",
                        },
                        {
                            "block_id": "body-4",
                            "type": "body_text",
                            "text": (
                                "The clearest current winner by volume is a mainstream "
                                "shade-range bundle built around beige, pink, red, and brown."
                            ),
                        },
                        {
                            "block_id": "table-4",
                            "type": "table",
                            "table_model": {
                                "header_rows": 1,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Shade Bundle"},
                                            {"text": "Top Sellers"},
                                            {"text": "Others"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Pink + Pink"},
                                            {"text": "91% (41 of 45)"},
                                            {"text": "67%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Brown + Brown"},
                                            {"text": "80% (36 of 45)"},
                                            {"text": "48%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Beige + Pink"},
                                            {"text": "76% (34 of 45)"},
                                            {"text": "39%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Beige + Red"},
                                            {"text": "69% (31 of 45)"},
                                            {"text": "30%"},
                                        ]
                                    },
                                ],
                            },
                        },
                        {
                            "block_id": "banner-4",
                            "type": "implication_banner",
                            "text": (
                                "Top-selling lines systematically cover this classic "
                                "nude/pink/red/brown territory much more heavily than the "
                                "rest of the market."
                            ),
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-5",
                            "type": "title",
                            "text": (
                                "The Performance Overlay: Long-Wear and Full Coverage"
                            ),
                        },
                        {
                            "block_id": "table-5",
                            "type": "table",
                            "table_model": {
                                "header_rows": 1,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Layer / Attribute"},
                                            {"text": "Top Sellers"},
                                            {"text": "Others"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Pink + Red + Long-wear"},
                                            {"text": "60%"},
                                            {"text": "29%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Beige + Pink + Long-wear"},
                                            {"text": "53%"},
                                            {"text": "23%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Pink + Red + Full Coverage"},
                                            {"text": "51%"},
                                            {"text": "23%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {
                                                "text": "Full Coverage + Liquid + Long-wear"
                                            },
                                            {"text": "24%"},
                                            {"text": "7%"},
                                        ]
                                    },
                                ],
                            },
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "brand-7",
                            "type": "text",
                            "text": (
                                "The top-seller cohort exhibits real brand concentration, "
                                "with BRAND ALPHA holding 9 of 45 products (2.49x over-index)."
                            ),
                        },
                        {
                            "block_id": "body-7",
                            "type": "body_text",
                            "text": (
                                "However, the main winning bundles survive contact with "
                                "this concentration; BRAND ALPHA provides amplitude, but not the "
                                "direction itself."
                            ),
                        },
                        {
                            "block_id": "banner-7",
                            "type": "implication_banner",
                            "text": (
                                "No major winning-now bundle collapses into a single-brand "
                                "artifact upon inspection."
                            ),
                        },
                        {
                            "block_id": "table-7",
                            "type": "table",
                            "table_model": {
                                "header_rows": 0,
                                "rows": [
                                    {
                                        "cells": [
                                            {"text": "Beige + Pink"},
                                            {"text": "Spans 17 brands"},
                                            {"text": "BRAND ALPHA accounts for 24%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {"text": "Pink + Red + Long-wear"},
                                            {"text": "Spans 16 brands"},
                                            {"text": "BRAND ALPHA accounts for 30%"},
                                        ]
                                    },
                                    {
                                        "cells": [
                                            {
                                                "text": "Full Coverage + Liquid + Long-wear"
                                            },
                                            {"text": "Spans 10 brands"},
                                            {"text": "No brand above 2 products"},
                                        ]
                                    },
                                ],
                            },
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "review-8a",
                            "type": "body_text",
                            "text": (
                                "Review evidence confirms the winning propositions "
                                "but establishes clear operational limits."
                            ),
                        },
                        {
                            "block_id": "review-8b",
                            "type": "body_text",
                            "text": (
                                "Shade accuracy and formula consistency remain "
                                "baseline category friction points."
                            ),
                        },
                    ],
                    "figure_regions": [],
                },
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    constants_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "stability_metric"
        and item["claim_text"].startswith("Constants:")
    )
    assert constants_claim["status"] == "verified"
    assert constants_claim["details"]["comparison_outcome"] == "pass"
    assert (
        constants_claim["details"]["aggregation_rule_id"] == "stability_metric_list_v1"
    )
    assert {
        item["entity"] for item in constants_claim["details"]["attribute_support"]
    } == {"pink", "red", "brown", "stick form", "matte finish"}

    divergence_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "divergence_summary"
        and item["claim_text"].startswith("The divergence:")
    )
    assert divergence_claim["status"] == "verified"
    assert divergence_claim["details"]["comparison_outcome"] == "pass"
    assert (
        divergence_claim["details"]["aggregation_rule_id"]
        == "divergence_explicit_care_v1"
    )
    assert (
        divergence_claim["details"]["row_support"][0]["zero_occurrence_check"][0][
            "passed"
        ]
        is True
    )

    winning_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
        and item["claim_text"].startswith("Winning now:")
    )
    assert winning_claim["status"] == "verified"
    assert winning_claim["details"]["comparison_outcome"] == "pass"
    assert winning_claim["details"]["aggregation_rule_id"] == (
        "winning_summary_synthesis_v1"
    )
    assert winning_claim["details"]["missing_components"] == []
    assert any(
        item["claim_family"] == "bundle_brand_concentration"
        for item in winning_claim["details"]["component_claims"]
    )
    assert any(
        item["claim_family"] == "review_validation"
        for item in winning_claim["details"]["component_claims"]
    )
    assert any(
        item["claim_family"] == "review_friction"
        for item in winning_claim["details"]["component_claims"]
    )

    review_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "review_validation"
        and item["claim_text"].startswith("Review evidence confirms")
    )
    assert review_claim["status"] == "verified"
    assert review_claim["details"]["comparison_outcome"] == "pass"
    assert review_claim["details"]["aggregation_rule_id"] == (
        "review_validation_summary_v1"
    )
    assert review_claim["details"]["cohort_basis"] == "top_seller_review_rows"
    assert not any(
        item["claim_family"] == "review_friction"
        and item["claim_text"].startswith("Review evidence confirms")
        for item in payload["claims"]
    )

    friction_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "review_friction"
        and item["claim_text"].startswith("Shade accuracy")
    )
    assert friction_claim["status"] == "verified"
    assert friction_claim["details"]["comparison_outcome"] == "pass"
    assert friction_claim["details"]["aggregation_rule_id"] == (
        "review_friction_topics_v1"
    )

    slide4_summary = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
        and item["claim_text"].startswith("The clearest current winner by volume")
    )
    assert slide4_summary["status"] == "verified"
    assert slide4_summary["details"]["comparison_outcome"] == "pass"


def test_validate_launch_report_pdf_partially_backs_summary_from_structural_component(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Long-wearing + Matte + Pressed powder",
                "count_top_seller": 6,
                "top_seller_base": 36,
                "count_other": 3,
                "other_base": 143,
                "pct_top_seller": 0.1666666667,
                "pct_other": 0.020979021,
                "prevalence_ratio": 7.944444,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "body_text",
                            "text": (
                                "Long-wearing + Matte + Pressed powder: "
                                "16.4% of top sellers vs 2.1% of others."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "The strongest current winner is long-wearing "
                                "pressed powder, fundamentally prioritizing "
                                "durability and format over overt glow."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    bundle_claim = next(
        item for item in payload["claims"] if item["claim_family"] == "bundle_metric"
    )
    assert bundle_claim["status"] == "partially_backed"
    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["comparison_outcome"] == "partial"
    assert summary_claim["details"]["component_claims"][0]["claim_family"] == (
        "bundle_metric"
    )
    assert summary_claim["details"]["component_claims"][0]["status"] == (
        "partially_backed"
    )


def test_validate_launch_report_pdf_contradicts_same_slide_summary_from_bad_components(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Long-wearing + Matte + Pressed powder",
                "count_top_seller": 6,
                "top_seller_base": 36,
                "count_other": 3,
                "other_base": 143,
                "pct_top_seller": 0.1666666667,
                "pct_other": 0.020979021,
                "prevalence_ratio": 7.944444,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "body_text",
                            "text": (
                                "Long-wearing + Matte + Pressed powder: "
                                "30.0% of top sellers vs 20.0% of others."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "The strongest current winner is long-wearing "
                                "pressed powder, fundamentally prioritizing "
                                "durability and format over overt glow."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    bundle_claim = next(
        item for item in payload["claims"] if item["claim_family"] == "bundle_metric"
    )
    assert bundle_claim["status"] == "contradicted"
    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "contradicted"
    assert summary_claim["details"]["comparison_outcome"] == "fail"
    assert summary_claim["details"]["component_claims"][0]["status"] == "contradicted"
    assert (
        "same-slide deterministic support components are contradicted"
        in summary_claim["details"]["reasons"]
    )


def test_validate_launch_report_pdf_requires_matching_component_for_brand_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Buildable + Pressed Powder",
                "count_top_seller": 21,
                "top_seller_brand_count": 16,
            },
            {
                "bundle_label": "Full + Liquid",
                "count_top_seller": 7,
                "top_seller_brand_count": 7,
            },
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "pressed-row",
                            "type": "body_text",
                            "text": (
                                "Buildable + Pressed Powder: Matched Products "
                                "26 Top Sellers; Brand Distribution 19 Brands "
                                "(Max brand share: 15%)"
                            ),
                        },
                        {
                            "block_id": "liquid-row",
                            "type": "body_text",
                            "text": (
                                "Full + Liquid: Matched Products 7 Top Sellers; "
                                "Brand Distribution 7 Brands"
                            ),
                        },
                        {
                            "block_id": "pressed-summary",
                            "type": "body_text",
                            "text": (
                                "Pressed-powder bundles strictly survive brand "
                                "concentration, confirming a genuinely multi-brand "
                                "architecture."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    pressed_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "bundle_brand_concentration"
        and item["claim_text"].startswith("Buildable + Pressed Powder:")
    )
    assert pressed_claim["status"] == "contradicted"

    liquid_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "bundle_brand_concentration"
        and item["claim_text"].startswith("Full + Liquid:")
    )
    assert liquid_claim["status"] == "verified"

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
        and item["claim_text"].startswith("Pressed-powder bundles")
    )
    assert summary_claim["status"] == "contradicted"
    assert summary_claim["details"]["comparison_outcome"] == "fail"
    assert summary_claim["details"]["component_claims"][0]["claim_text"].startswith(
        "Buildable + Pressed Powder:"
    )
    assert not any(
        item["claim_text"].startswith("Full + Liquid:")
        for item in summary_claim["details"]["component_claims"]
    )


def test_validate_launch_report_pdf_partially_backs_stable_core_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Long-wearing + Matte + Pressed powder",
                "count_top_seller": 6,
                "top_seller_base": 36,
                "count_other": 3,
                "other_base": 143,
                "pct_top_seller": 0.1666666667,
                "pct_other": 0.020979021,
                "prevalence_ratio": 7.944444,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "body_text",
                            "text": (
                                "Long-wearing + Matte + Pressed powder: "
                                "16.4% of top sellers vs 2.1% of others."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Stable Core: The category is dominated by matte "
                                "pressed powders claiming long-wear durability."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["component_claims"][0]["claim_family"] == (
        "bundle_metric"
    )
    assert summary_claim["details"]["component_claims"][0]["status"] == (
        "partially_backed"
    )


def test_validate_launch_report_pdf_partially_backs_aligning_with_baseline_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Long-wearing + Matte + Pressed powder",
                "count_top_seller": 6,
                "top_seller_base": 36,
                "count_other": 3,
                "other_base": 143,
                "pct_top_seller": 0.1666666667,
                "pct_other": 0.020979021,
                "prevalence_ratio": 7.944444,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "body_text",
                            "text": (
                                "Long-wearing + Matte + Pressed powder: "
                                "16.4% of top sellers vs 2.1% of others."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "PDP emphasizes long-wearing satin cream and "
                                "velvet powder, aligning with the Long-wearing "
                                "+ Matte/Natural baseline."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["component_claims"][0]["claim_family"] == (
        "bundle_metric"
    )


def test_validate_launch_report_pdf_partially_backs_directly_embodies_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "innovation_triples.csv",
        [
            {
                "bundle_label": "Luminous + Stick + Hydrating",
                "count_recent": 4,
                "recent_base": 34,
                "count_rest": 5,
                "rest_base": 152,
                "pct_recent": 0.1176470588,
                "pct_rest": 0.0328947368,
                "prevalence_ratio": 3.5764705882,
            }
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "body_text",
                            "text": (
                                "Luminous + Stick + Hydrating: Recent vs Rest "
                                "Prevalence 11.8% vs 3.3%."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Directly embodies the strongest emerging "
                                "stick-hybrid signal."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["component_claims"][0]["claim_family"] == (
        "bundle_metric"
    )
    assert summary_claim["details"]["component_claims"][0]["status"] == "verified"


def test_validate_launch_report_pdf_partially_backs_plural_component_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "pullover + crewneck + long sleeve",
                "count_top_seller": 10,
                "top_seller_base": 48,
                "count_other": 2,
                "other_base": 100,
                "pct_top_seller": 0.2083333333,
                "pct_other": 0.02,
                "prevalence_ratio": 10.41666667,
            }
        ],
    )
    pdf_path = tmp_path / "cashmere.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "body_text",
                            "text": (
                                "pullover + crewneck + long sleeve: "
                                "Top-Seller Penetration 20.8% vs 2.0% of others."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Winning products are visually conventional "
                                "cardigans and pullovers featuring ribbed hems, "
                                "crewnecks, and understated premium construction."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["component_claims"][0]["claim_family"] == (
        "bundle_metric"
    )


def test_validate_launch_report_pdf_partially_backs_synonym_component_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Buildable + Luminous",
                "count_top_seller": 10,
                "top_seller_base": 50,
                "count_other": 10,
                "other_base": 100,
                "pct_top_seller": 0.2,
                "pct_other": 0.1,
                "prevalence_ratio": 2.0,
            }
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "body_text",
                            "text": (
                                "Buildable + Luminous: 20.0% of top sellers "
                                "vs 10.0% of others."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Hydration functions meaningfully in recent "
                                "products primarily as an add-on to buildability "
                                "and glow."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["component_claims"][0]["claim_family"] == (
        "bundle_metric"
    )


def test_validate_launch_report_pdf_checks_emerging_signal_summary_against_innovation_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low top sneakers",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "multicolor + runner-inspired",
                "count_recent": 6,
                "count_rest": 7,
                "recent_base": 42,
                "rest_base": 165,
                "pct_recent": 0.1428571429,
                "pct_rest": 0.0424242424,
                "prevalence_ratio": 3.367347,
                "recent_brand_count": 3,
                "rest_brand_count": 7,
                "insight_adjusted_signal_score": 27.439208,
            },
            {
                "bundle_label": "multicolor + leather",
                "count_recent": 14,
                "count_rest": 21,
                "recent_base": 42,
                "rest_base": 165,
                "pct_recent": 0.3333333333,
                "pct_rest": 0.1272727273,
                "prevalence_ratio": 2.619048,
                "recent_brand_count": 10,
                "rest_brand_count": 18,
                "insight_adjusted_signal_score": 25.958442,
            },
            {
                "bundle_label": "runner-inspired + rubber sole",
                "count_recent": 3,
                "count_rest": 0,
                "recent_base": 42,
                "rest_base": 165,
                "pct_recent": 0.0714285714,
                "pct_rest": 0.0,
                "prevalence_ratio": None,
                "recent_brand_count": 2,
                "rest_brand_count": 0,
                "insight_adjusted_signal_score": 8.157143,
            },
        ],
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Recent product introductions reinforce the baseline "
                                "while adding a secondary layer of multicolor and "
                                "technical/runner-inspired expression."
                            ),
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-6",
                    "slide_number": 6,
                    "page_number": 6,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-2",
                            "type": "body_text",
                            "text": (
                                "The most credible emerging signal is the integration "
                                "of multicolor expression."
                            ),
                        },
                    ],
                    "figure_regions": [],
                },
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    secondary_layer_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Recent product introductions")
    )
    assert secondary_layer_claim["status"] == "verified"
    assert secondary_layer_claim["claim_family"] == "summary_synthesis"
    assert secondary_layer_claim["details"]["aggregation_rule_id"] == (
        "emerging_signal_summary_v1"
    )
    assert secondary_layer_claim["details"]["row_support"][0]["source_file"] == (
        "innovation_pairs.csv"
    )
    assert secondary_layer_claim["details"]["row_support"][0]["matched_tokens"] == [
        "inspired",
        "multicolor",
        "runner",
    ]

    superlative_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("The most credible emerging signal")
    )
    assert superlative_claim["status"] == "partially_backed"
    assert superlative_claim["details"]["comparison_outcome"] == "partial"
    assert superlative_claim["details"]["aggregation_rule_id"] == (
        "emerging_signal_summary_v1"
    )


def test_validate_launch_report_pdf_checks_current_winner_format_summary_against_top_seller_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "Pate + Vitamins & Minerals + Can",
                "count_top_seller": 117,
                "count_other": 249,
                "top_seller_base": 633,
                "other_base": 2531,
                "pct_top_seller": 0.1848341232,
                "pct_other": 0.098380087,
                "prevalence_ratio": 1.8787757666,
                "top_seller_brand_count": 17,
                "other_brand_count": 46,
            }
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Pâté in cans represents one of the cleanest "
                                "current winning formats on the shelf."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "summary_synthesis"
    )
    assert summary_claim["status"] == "partially_backed"
    assert summary_claim["details"]["comparison_outcome"] == "partial"
    assert summary_claim["details"]["aggregation_rule_id"] == (
        "current_winner_format_summary_v1"
    )
    assert summary_claim["details"]["row_support"][0]["source_file"] == (
        "top_seller_triples.csv"
    )
    assert summary_claim["details"]["row_support"][0]["matched_tokens"] == [
        "can",
        "pate",
    ]


def test_validate_launch_report_pdf_checks_pdp_descriptor_summary_against_same_slide_winner_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "Chunks in Gravy + Can",
                "count_top_seller": 235,
                "count_other": 440,
                "top_seller_base": 633,
                "other_base": 2531,
                "pct_top_seller": 0.3712480253,
                "pct_other": 0.1738443303,
                "prevalence_ratio": 2.1355206,
                "top_seller_brand_count": 27,
                "other_brand_count": 52,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "parent_product_id": "winner-1",
                "product_name": "Chicken Chunks in Savory Gravy Canned Cat Food",
                "brand": "Synthetic Pet Brand A",
                "food texture": "Chunks in Gravy",
                "packaging type": "Can",
                "description": (
                    "Savory gravy with real meat aroma and moisture-rich gravy "
                    "for hydration support."
                ),
            },
            {
                "parent_product_id": "winner-2",
                "product_name": "Turkey Chunks in Gravy Cans",
                "brand": "Synthetic Pet Brand B",
                "food texture": "Chunks in Gravy",
                "packaging type": "Can",
                "description": (
                    "Tender meat aroma in savoury gravy with broth and moisture "
                    "for everyday hydration."
                ),
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Chunks in gravy in cans operate as the secondary "
                                "primary pillar of current market winners."
                            ),
                        },
                        {
                            "block_id": "summary-2",
                            "type": "body_text",
                            "text": (
                                "Product detail pages for these winners explicitly "
                                "reinforce savory gravy, meat aroma, and hydration."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    pdp_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Product detail pages")
    )
    assert pdp_claim["status"] == "verified"
    assert pdp_claim["claim_family"] == "summary_synthesis"
    assert pdp_claim["details"]["aggregation_rule_id"] == ("pdp_descriptor_summary_v1")
    assert pdp_claim["details"]["component_entities"] == ["Chunks in Gravy + Can"]
    topic_counts = pdp_claim["details"]["row_support"][0]["topic_counts"]
    assert topic_counts["savory_gravy"] == {"match_count": 2, "brand_count": 2}
    assert topic_counts["meat_aroma"] == {"match_count": 2, "brand_count": 2}
    assert topic_counts["hydration"] == {"match_count": 2, "brand_count": 2}


def test_validate_launch_report_pdf_checks_format_constraint_summary_against_top_seller_products(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Tray Winner 1",
                "brand": "Pet Brand Gamma",
                "packaging type": "Tray",
            },
            {
                "product_name": "Tray Winner 2",
                "brand": "Pet Brand Gamma",
                "packaging type": "Tray",
            },
            {
                "product_name": "Tray Winner 3",
                "brand": "Pet Brand Gamma",
                "packaging type": "Tray",
            },
            {
                "product_name": "Tray Winner 4",
                "brand": "Pet Brand Gamma",
                "packaging type": "Tray",
            },
            {
                "product_name": "Tray Winner 5",
                "brand": "Pet Brand Alpha",
                "packaging type": "Tray",
            },
            {
                "product_name": "Tray Winner 6",
                "brand": "Pet Brand Alpha",
                "packaging type": "Tray",
            },
            {
                "product_name": "Can Winner 1",
                "brand": "Brand A",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 2",
                "brand": "Brand B",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 3",
                "brand": "Brand C",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 4",
                "brand": "Brand D",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 5",
                "brand": "Brand E",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 6",
                "brand": "Brand F",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 7",
                "brand": "Brand G",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 8",
                "brand": "Brand H",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 9",
                "brand": "Brand I",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 10",
                "brand": "Brand J",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 11",
                "brand": "Brand K",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 12",
                "brand": "Brand L",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 13",
                "brand": "Brand M",
                "packaging type": "Can",
            },
            {
                "product_name": "Can Winner 14",
                "brand": "Brand N",
                "packaging type": "Can",
            },
        ],
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-6",
                    "slide_number": 6,
                    "page_number": 6,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Tray winners are product-real, but heavily "
                                "brand- and packaging-constrained."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Tray winners")
    )
    assert summary_claim["status"] == "verified"
    assert summary_claim["details"]["aggregation_rule_id"] == (
        "format_constraint_summary_v1"
    )
    support = summary_claim["details"]["row_support"][0]
    assert support["matched_row_keys"] == {
        "attribute_column": "packaging type",
        "attribute_value": "Tray",
    }
    assert support["computed_values"]["product_count"] == 6
    assert support["computed_values"]["brand_count"] == 2
    assert support["computed_values"]["top_seller_share"] == 0.3


def test_validate_launch_report_pdf_checks_attribute_penetration_summary_against_mapped_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "style",
                "attribute_value": "oversized",
                "count_recent": 8,
                "count_rest": 37,
                "recent_base": 14,
                "rest_base": 46,
                "pct_recent": 0.5714285714,
                "pct_rest": 0.8043478261,
                "delta": -0.2329192547,
            }
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Secondary modifiers like 'oversized' "
                                "(76.7% penetration) augment this spine but "
                                "do not replace it."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Secondary modifiers")
    )
    assert summary_claim["status"] == "contradicted"
    assert summary_claim["details"]["aggregation_rule_id"] == (
        "attribute_penetration_summary_v1"
    )
    support = summary_claim["details"]["row_support"][0]
    assert support["matched_row_keys"] == {
        "attribute_name": "style",
        "attribute_value": "oversized",
    }
    assert support["computed_values"]["combined_recent_rest_percent"] == 75.0


def test_validate_launch_report_pdf_checks_material_composition_summary_against_top_seller_products(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Cashmere Cardigan",
                "brand": "Brand A",
                "description": "Pure cashmere long-sleeve cardigan.",
            },
            {
                "product_name": "Wool-Cashmere Sweater",
                "brand": "Brand B",
                "description": "A sweater made of wool and cashmere.",
            },
            {
                "product_name": "Stretch-Cashmere Sweater",
                "brand": "Brand C",
                "description": "Soft stretch-cashmere knit.",
            },
            {
                "product_name": "Cashmere-Blend Pullover",
                "brand": "Brand D",
                "description": "A cashmere blend pullover.",
            },
            {
                "product_name": "Classic Cashmere Crewneck",
                "brand": "Brand E",
                "description": "Classic cashmere sweater.",
            },
        ],
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-5",
                    "slide_number": 5,
                    "page_number": 5,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "The winning proposition is specifically "
                                "cashmere-led luxury knitwear, with some "
                                "top-sellers utilizing wool/cashmere or stretch "
                                "blends."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    summary_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("The winning proposition is specifically")
    )
    assert summary_claim["status"] == "verified"
    assert summary_claim["claim_family"] == "summary_synthesis"
    assert summary_claim["details"]["aggregation_rule_id"] == (
        "material_composition_summary_v1"
    )
    support = summary_claim["details"]["row_support"][0]
    assert support["computed_values"]["cashmere_product_share"] == 1.0
    assert support["computed_values"]["variant_product_count"] == 3
    assert support["computed_values"]["variant_brand_count"] == 3


def test_validate_launch_report_pdf_checks_contextual_product_brand_share_against_top_seller_products(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
        retailer="ulta",
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Delta Hydrating Stick 1",
                "brand": "Delta Cosmetics",
                "form": "Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
            {
                "product_name": "Delta Hydrating Stick 2",
                "brand": "Delta Cosmetics",
                "form": "Cream pot | Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
            {
                "product_name": "Delta Hydrating Stick 3",
                "brand": "Delta Cosmetics",
                "form": "stain | Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
            {
                "product_name": "Meadow Hydrating Stick 1",
                "brand": "MEADOW COSMETICS",
                "form": "Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
            {
                "product_name": "Meadow Hydrating Stick 2",
                "brand": "MEADOW COSMETICS",
                "form": "Cream pot | Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
            {
                "product_name": "Cedar Hydrating Stick",
                "brand": "Cedar Cosmetics",
                "form": "Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
            {
                "product_name": "Terra Hydrating Stick",
                "brand": "Terra Cosmetics",
                "form": "Cream pot | Pressed powder | Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
            {
                "product_name": "Boreal Hydrating Stick",
                "brand": "BOREAL COSMETICS",
                "form": "Stick",
                "resolved_form": "Stick",
                "form_children": "stick",
                "skin benefits": "Hydrating",
            },
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Demonstrates higher brand concentration "
                                "(Delta accounts for ~40% of matched top-seller "
                                "set for hydrating sticks)."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Demonstrates higher brand concentration")
    )
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_brand_concentration"
    assert claim["details"]["aggregation_rule_id"] == (
        "contextual_product_brand_share_v1"
    )
    support = claim["details"]["row_support"][0]
    assert support["computed_values"]["matched_product_count"] == 8
    assert support["computed_values"]["brand_product_count"] == 3
    assert support["computed_values"]["brand_share"] == 37.5


def test_validate_launch_report_pdf_checks_sale_pressure_bundle_concentration_summary_against_sale_pressure_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low top sneakers",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "sale_pressure_pairs.csv",
        [
            {
                "bundle_label": "colorblock + round toe",
                "bundle_key": "color=colorblock + toe_shape=round toe",
                "count_sale_pressure": 22,
                "sale_pressure_base": 96,
                "pct_sale_pressure": 0.2291666667,
                "count_not_observed_sale_pressure": 8,
                "not_observed_sale_pressure_base": 111,
                "pct_not_observed_sale_pressure": 0.0720720721,
                "sale_pressure_brand_count": 14,
            },
            {
                "bundle_label": "lace-up + colorblock",
                "bundle_key": "closure=lace-up + color=colorblock",
                "count_sale_pressure": 19,
                "sale_pressure_base": 96,
                "pct_sale_pressure": 0.1979166667,
                "count_not_observed_sale_pressure": 10,
                "not_observed_sale_pressure_base": 111,
                "pct_not_observed_sale_pressure": 0.0900900901,
                "sale_pressure_brand_count": 14,
            },
        ],
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Sale-pressure concentration is stronger around "
                                "specific bundles:"
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Sale-pressure concentration")
    )
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "sale_pressure_exposure"
    assert claim["details"]["aggregation_rule_id"] == (
        "sale_pressure_bundle_concentration_summary_v1"
    )
    assert len(claim["details"]["row_support"]) == 2
    assert claim["details"]["component_entities"] == [
        "colorblock + round toe",
        "lace-up + colorblock",
    ]
    assert (
        claim["details"]["row_support"][0]["computed_values"]["delta_pct_points"]
        == 15.7095
    )


def test_validate_launch_report_pdf_checks_core_bundle_brand_promotion_resilience(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "cardigan + long sleeve",
                "bundle_key": "garment type=cardigan + sleeve length=long sleeve",
                "count_top_seller": 6,
                "top_seller_brand_count": 5,
                "top_seller_base": 20,
                "pct_top_seller": 0.30,
            },
            {
                "bundle_label": "black + rib-knit",
                "bundle_key": "color=black + knit_detail=rib-knit",
                "count_top_seller": 5,
                "top_seller_brand_count": 4,
                "top_seller_base": 20,
                "pct_top_seller": 0.25,
            },
            {
                "bundle_label": "cable-knit + long sleeve",
                "bundle_key": "bundle-b",
                "count_top_seller": 4,
                "top_seller_brand_count": 4,
                "top_seller_base": 20,
                "pct_top_seller": 0.20,
            },
        ],
    )
    _write_csv(package_dir / "top_seller_triples.csv", [])
    product_rows: list[dict[str, object]] = [
        {
            "product_name": f"Cardigan {index}",
            "brand": f"Brand {index}",
            "garment type": "cardigan",
            "sleeve length": "long sleeve",
            "color": "grey",
            "knit_detail": "plain",
            "sale_pressure_status": (
                "sale_pressure" if index == 1 else "not_observed_sale_pressure"
            ),
        }
        for index in range(1, 7)
    ]
    product_rows.extend(
        {
            "product_name": f"Black rib-knit {index}",
            "brand": f"Rib Brand {index}",
            "garment type": "pullover",
            "sleeve length": "long sleeve",
            "color": "black",
            "knit_detail": "rib-knit",
            "sale_pressure_status": "not_observed_sale_pressure",
        }
        for index in range(1, 6)
    )
    product_rows.extend(
        {
            "product_name": f"Cable knit {index}",
            "brand": f"Cable Brand {index}",
            "garment type": "pullover",
            "sleeve length": "long sleeve",
            "color": "cream",
            "knit_detail": "cable-knit",
            "sale_pressure_status": (
                "sale_pressure" if index == 1 else "not_observed_sale_pressure"
            ),
        }
        for index in range(1, 5)
    )
    _write_csv(package_dir / "top_seller_products.csv", product_rows)
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-12",
                    "slide_number": 12,
                    "page_number": 12,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Core architectural bundles survive brand "
                                "concentration and remain mostly unassisted by "
                                "promotional pressure, validating the organic "
                                "strength of the primary signals."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Core architectural bundles survive")
    )
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_brand_concentration"
    assert claim["details"]["aggregation_rule_id"] == (
        "core_bundle_brand_promotion_resilience_v1"
    )
    metrics = claim["details"]["summary_metrics"]
    assert metrics["core_bundle_row_count"] == 3
    assert metrics["sale_pressure_measured_row_count"] == 3
    assert metrics["low_sale_pressure_share"] == 1.0


def test_validate_launch_report_pdf_checks_baseline_visibility_recent_construction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
        retailer="ulta",
    )
    _write_csv(
        package_dir / "filter_comparison.csv",
        [
            {
                "filter_family": "color",
                "filter_value": "pink",
                "count_recent": 34,
                "count_rest": 148,
                "recent_family_base": 39,
                "rest_family_base": 151,
                "pct_recent": 0.8717948718,
                "pct_rest": 0.9801324503,
            }
        ],
    )
    _write_csv(
        package_dir / "web_shelf_robustness_summary.csv",
        [
            {
                "bundle_key": "color=pink + spf=15 - 30",
                "times_selected": 4,
                "best_shelf_rank": 1,
                "average_gross_weight_share": 0.6801966212,
                "gross_sku_count": 177,
                "gross_brand_count": 78,
            }
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "Pink represents baseline visibility: Pink shade "
                                "presence explains rank-weighted shelf visibility "
                                "but is actually lower in recent product "
                                "construction."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Pink represents baseline visibility")
    )
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "attribute_direction"
    assert claim["details"]["aggregation_rule_id"] == (
        "baseline_visibility_recent_construction_v1"
    )
    support = claim["details"]["row_support"][0]
    assert support["computed_values"]["baseline_presence_pct"] == 98.0132
    assert support["computed_values"]["recent_decline_pct_points"] == 10.8338


def test_validate_launch_report_pdf_resolves_product_exemplars_and_attributes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    product_rows = [
        {
            "product_name": "Brand Alpha Silky Matte Lipstick",
            "brand": "BRAND ALPHA",
            "parent_product_id": "brand-alpha-silky-matte",
            "pareto_rank": 2,
            "pareto_bucket": "A",
            "top_seller_status": "top_seller",
            "price_band": "value",
            "entry_price": 17.5,
            "resolved_finish": "matte",
            "resolved_coverage": "full coverage",
            "resolved_color": "beige | pink | red | brown | wine",
            "resolved_form": "cream | stick",
            "benefits": "nourishing/conditioning",
            "coverage": "full coverage",
            "form": "bullet lipstick",
            "wear claims": "long-wear",
            "summary": (
                "Pigment-rich, full coverage colour with a silky-matte finish "
                "and 12 hours of longwear."
            ),
            "description_excerpt": (
                "Conditions and nourishes lips with comfortable matte wear."
            ),
        },
        {
            "product_name": "Brand Alpha Mini Silky Matte Lipstick",
            "brand": "BRAND ALPHA",
            "parent_product_id": "brand-alpha-silky-matte-mini",
            "pareto_rank": 14,
            "pareto_bucket": "A",
            "top_seller_status": "top_seller",
            "price_band": "value",
            "entry_price": 14.0,
            "resolved_finish": "matte",
            "resolved_coverage": "full coverage",
            "resolved_color": "beige | pink | red",
            "resolved_form": "stick",
            "benefits": "smoothing/blur",
            "coverage": "full coverage",
            "form": "bullet lipstick",
            "wear claims": "long-wear",
            "summary": (
                "Mini pigment-rich matte lipstick with full coverage colour and longwear."
            ),
            "description_excerpt": ("Mini form with comfortable matte wear."),
        },
        {
            "product_name": "Brand Lambda Hydrating Shine Lipstick",
            "brand": "BRAND LAMBDA",
            "parent_product_id": "brand-lambda-hydrating-shine",
            "pareto_rank": 35,
            "pareto_bucket": "A",
            "top_seller_status": "top_seller",
            "price_band": "premium",
            "entry_price": 50.0,
            "resolved_finish": "high shine",
            "resolved_coverage": "full coverage",
            "resolved_color": "red | pink | wine | beige",
            "resolved_form": "cream | stick",
            "benefits": "hydrating/moisturizing",
            "coverage": "full coverage",
            "form": "bullet lipstick",
            "wear claims": "long-wear",
            "summary": (
                "Transforms on contact with lips for an enhanced high-shine "
                "effect and moisturizing comfort."
            ),
            "description_excerpt": (
                "The formula glides smoothly onto lips and ensures nourishing comfort."
            ),
        },
        {
            "product_name": "Brand Mu Long Lasting Matte Lip Tint",
            "brand": "BRAND MU",
            "parent_product_id": "brand-mu-matte-tint",
            "pareto_rank": 18,
            "pareto_bucket": "A",
            "top_seller_status": "top_seller",
            "price_band": "value",
            "entry_price": 12.99,
            "resolved_finish": "matte",
            "resolved_coverage": "buildable coverage",
            "resolved_color": "brown | pink | red | wine",
            "resolved_form": "cream | tint",
            "benefits": "smoothing/blur",
            "coverage": "buildable coverage",
            "form": "lip tint/stain",
            "wear claims": "long-wear",
            "summary": ("Wear it sheer, blurred, bold or even on cheeks."),
            "description_excerpt": (
                "A plush, blurred matte color look with buildable shades for lips "
                "or cheeks."
            ),
        },
    ]
    _write_csv(package_dir / "top_seller_products.csv", product_rows)
    _write_csv(
        package_dir / "recent_products.csv",
        [product_rows[0], product_rows[2]],
    )
    _write_csv(
        package_dir / "recent_product_pdp_extracts.csv",
        [product_rows[0], product_rows[3]],
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        product_rows
        + [
            {
                "product_name": "Brand Kappa Luxe Matte Lipstick",
                "brand": "BRAND KAPPA",
                "parent_product_id": "brand-kappa-luxe-matte",
                "price_band": "premium",
                "entry_price": 45.0,
                "resolved_coverage": "buildable coverage",
                "benefits": "smoothing/blur",
                "summary": "Soft-focus premium lipstick with buildable payoff.",
            }
        ],
    )

    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-006.html",
                    "slide_number": 6,
                    "page_number": 6,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-0",
                            "type": "bullet_item",
                            "items": [
                                "Brand Alpha Silky Matte Lipstick (Rank #2 in top sellers) directly embodies the strongest data bundle.",
                                "It combines mainstream shade coverage with full coverage, long-wear, and matte performance.",
                            ],
                        }
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-010.html",
                    "slide_number": 10,
                    "page_number": 10,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-0",
                            "type": "bullet_item",
                            "items": [
                                "Brand Lambda Hydrating Shine Lipstick represents the cleanest premium expression of this emerging lane.",
                                "It sits squarely at the intersection of high-shine finish, hydrating language, and stick form within the red/pink/wine spectrum.",
                            ],
                        }
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-012.html",
                    "slide_number": 12,
                    "page_number": 12,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-0",
                            "type": "bullet_item",
                            "items": [
                                "This confirms that the buildable/blur story spans from mass to prestige pricing tiers.",
                                "explicitly promises buildable payoff, a soft-focus tint, and multi-use flexibility while retaining long-wear expectations.",
                            ],
                        },
                        {
                            "block_id": "block-1",
                            "type": "exhibit_label",
                            "text": (
                                "Exhibit C: Brand Mu Long Lasting Matte Lip Tint. "
                                "Validation of the buildable, blurred, tint-like long-wear system."
                            ),
                        },
                    ],
                    "figure_regions": [],
                },
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    alpha_exemplar = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "product_exemplar" and item["slide_number"] == 6
    )
    assert alpha_exemplar["status"] == "verified"
    assert alpha_exemplar["details"]["normalized_product_name"] == (
        "Brand Alpha Silky Matte Lipstick"
    )
    assert alpha_exemplar["details"]["rank_value"] == 2
    assert set(alpha_exemplar["details"]["matched_attribute_flags"]) >= {
        "mainstream_shade_coverage",
        "full_coverage",
        "long_wear",
        "matte",
    }

    alpha_attributes = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "product_attribute" and item["slide_number"] == 6
    )
    assert alpha_attributes["status"] == "verified"
    assert set(alpha_attributes["details"]["matched_attribute_flags"]) >= {
        "mainstream_shade_coverage",
        "full_coverage",
        "long_wear",
        "matte",
    }

    lambda_exemplar = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "product_exemplar" and item["slide_number"] == 10
    )
    assert lambda_exemplar["status"] == "verified"
    assert lambda_exemplar["details"]["normalized_product_name"] == (
        "Brand Lambda Hydrating Shine Lipstick"
    )
    assert lambda_exemplar["details"]["price_tier"] == "premium"
    assert set(lambda_exemplar["details"]["matched_attribute_flags"]) >= {
        "premium_tier",
        "high_shine",
        "hydrating_language",
        "stick_form",
        "red_pink_wine_spectrum",
    }

    lambda_attributes = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "product_attribute" and item["slide_number"] == 10
    )
    assert lambda_attributes["status"] == "verified"
    assert set(lambda_attributes["details"]["matched_attribute_flags"]) >= {
        "high_shine",
        "hydrating_language",
        "stick_form",
        "red_pink_wine_spectrum",
    }

    tier_span = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "product_tier_span"
    )
    assert tier_span["status"] == "verified"
    assert tier_span["details"]["price_tiers"] == ["premium", "value"]

    mu_exemplar = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "product_exemplar" and item["slide_number"] == 12
    )
    assert mu_exemplar["status"] == "verified"
    assert (
        "Brand Mu Long Lasting Matte Lip Tint"
        in mu_exemplar["details"]["normalized_product_name"]
    )
    assert set(mu_exemplar["details"]["matched_attribute_flags"]) >= {
        "buildable_coverage",
        "soft_focus_blur",
        "tint_like",
        "long_wear",
    }

    mu_attributes = next(
        item
        for item in payload["claims"]
        if item["claim_family"] == "product_attribute" and item["slide_number"] == 12
    )
    assert mu_attributes["status"] == "verified"
    assert set(mu_attributes["details"]["matched_attribute_flags"]) >= {
        "buildable_coverage",
        "soft_focus_blur",
        "tint_like",
        "multi_use_flexibility",
        "long_wear",
    }


def test_validate_launch_report_pdf_ignores_exhibit_product_label_without_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Brand Mosaic Cheek Tone Duo",
                "brand": "Brand Mosaic",
                "parent_product_id": "brand-mosaic-cheek-duo",
                "top_seller_status": "top_seller",
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "exhibit-label",
                            "type": "body_text",
                            "text": "Exhibit A: Brand Mosaic Cheek Tone Duo",
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert not any(
        item["claim_family"] == "product_exemplar" for item in payload["claims"]
    )
    assert not any(
        item.get("claim_text") == "Exhibit A: Brand Mosaic Cheek Tone Duo"
        for item in payload["unresolved"]
    )


def test_validate_launch_report_pdf_uses_adjacent_product_label_for_product_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    product_rows = [
        {
            "product_name": "Brand Mosaic Cheek Tone Duo",
            "brand": "Brand Mosaic",
            "parent_product_id": "brand-mosaic-cheek-duo",
            "pareto_rank": 2,
            "pareto_bucket": "A",
            "top_seller_status": "top_seller",
            "resolved_form": "Cream in pot/pan | Pressed powder",
            "form": "Cream pot | Pressed powder",
            "description_excerpt": (
                "Two-pan compact with a satin cream and velvet powder."
            ),
            "reviews_positive_headline": "Smooth texture",
            "reviews_positive_comment": (
                "The cream and powder feel smooth and velvety, blend easily, "
                "and have strong color payoff."
            ),
            "reviews_negative_headline": "Little payoff",
            "reviews_negative_comment": (
                "The packaging is nice but I had to layer for enough payoff."
            ),
            "rating": 4.8,
            "review_count": 425,
        },
        {
            "product_name": "Delta Cosmetics Dual Blush and Bronzer Stick",
            "brand": "Delta Cosmetics",
            "parent_product_id": "delta-dual-stick",
            "pareto_rank": 1,
            "pareto_bucket": "A",
            "top_seller_status": "top_seller",
            "resolved_coverage": "Buildable",
            "resolved_form": "Cream in pot/pan | Stick form",
            "benefits": "Hydrating",
            "description_excerpt": (
                "Creamy, buildable, blendable, streak-free application."
            ),
            "rating": 4.7,
            "review_count": 4668,
        },
    ]
    _write_csv(package_dir / "top_seller_products.csv", product_rows)
    _write_csv(package_dir / "recent_products.csv", product_rows)
    _write_csv(package_dir / "product_filter_matrix.csv", product_rows)
    _write_csv(package_dir / "recent_product_pdp_extracts.csv", product_rows)
    _write_csv(
        package_dir / "top_seller_review_validation.csv",
        [
            {
                **product_rows[0],
                "bundle_label": "Long-wearing + Pressed powder",
            }
        ],
    )
    _write_csv(package_dir / "bundle_review_validation.csv", [])

    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "label",
                            "type": "body_text",
                            "text": ("Exhibit A: Brand Mosaic Cheek Tone Duo"),
                        },
                        {
                            "block_id": "claims",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "Two-pan compact confirms the convergence of "
                                    "cream and powder forms within single SKUS."
                                ),
                                (
                                    "Reviews validate texture and blend, but expose "
                                    "friction around limited color payoff."
                                ),
                            ],
                        },
                    ],
                    "figure_regions": [],
                },
                {
                    "slide_id": "slide-10",
                    "slide_number": 10,
                    "page_number": 10,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "label",
                            "type": "body_text",
                            "text": (
                                "Exhibit B: Delta Cosmetics Dual Blush and "
                                "Bronzer Stick"
                            ),
                        },
                        {
                            "block_id": "claim",
                            "type": "bullet_item",
                            "items": [
                                (
                                    '"Creamy, buildable, streak-free" attributes '
                                    "match the hydrating/buildable signals."
                                )
                            ],
                        },
                    ],
                    "figure_regions": [],
                },
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    compact_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Two-pan compact")
    )
    assert compact_claim["status"] == "verified"
    assert compact_claim["claim_family"] == "product_attribute"
    assert compact_claim["details"]["normalized_product_name"] == (
        "Brand Mosaic Cheek Tone Duo"
    )

    review_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith("Reviews validate texture")
    )
    assert review_claim["status"] == "verified"
    assert review_claim["claim_family"] == "review_validation"

    delta_claim = next(
        item
        for item in payload["claims"]
        if item["claim_text"].startswith('"Creamy, buildable')
    )
    assert delta_claim["status"] == "verified"
    assert delta_claim["claim_family"] == "product_attribute"
    assert set(delta_claim["details"]["matched_attribute_flags"]) >= {
        "buildable_coverage",
        "creamy_texture",
        "streak_free",
    }


def test_load_launch_package_data_keeps_existing_package_metric_rows(
    tmp_path: Path,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "coverage=Full + form=Liquid",
                "bundle_label": "Full + Liquid",
                "count_top_seller": 1,
                "count_other": 1,
                "top_seller_base": 1,
                "other_base": 2,
                "pct_top_seller": 1.0,
                "pct_other": 0.5,
                "prevalence_ratio": 2.0,
            }
        ],
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {
                "product_name": "Top liquid",
                "brand": "A",
                "top_seller_status": "top_seller",
                "coverage": "Full",
                "form": "Liquid",
            },
            {
                "product_name": "Other liquid 1",
                "brand": "B",
                "top_seller_status": "other",
                "coverage": "Full",
                "form": "Liquid",
            },
            {
                "product_name": "Other liquid 2",
                "brand": "C",
                "top_seller_status": "other",
                "coverage": "Full",
                "form": "Liquid",
            },
        ],
    )

    frames = validator.load_launch_package_data(package_dir).frames

    row = frames["top_seller_pairs.csv"].to_dicts()[0]
    assert row["count_other"] == 1
    assert row["pct_other"] == 0.5
    assert "calculation_helper_id" not in row


def test_bundle_matching_handles_ocr_fused_bundle_terms() -> None:
    segment = "Natural+Stickform(16.2%recentvs 7.6% rest)"
    span = validator._best_bundle_span(segment, "Natural + Stick form")
    labels = validator._matched_bundle_labels(
        segment,
        validator._bundle_records(["Natural", "Natural + Stick form"]),
    )

    assert span is not None
    assert labels[0] == "Natural + Stick form"


def test_percent_mentions_match_approximate_ranges() -> None:
    mentions = validator._percent_mentions(
        "multicolor / striped + long sleeve: ~6-10% recent penetration"
    )

    assert mentions
    assert validator._percent_matches(mentions[0], 5.9405940594059405)


def test_accounts_for_brand_name_ignores_introductory_parenthetical_text() -> None:
    brand_name = validator._extract_accounts_for_brand_name(
        "Demonstrates higher brand concentration (Del Ta accounts for ~40% of matched top-seller set)"
    )

    assert brand_name == "Del Ta"
    assert validator._brand_names_compatible(brand_name, "Delta Cosmetics")


def test_best_stability_candidate_prefers_filter_prevalence_surface(
    tmp_path: Path,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "filter_comparison.csv",
        [
            {
                "filter_family": "color lips",
                "filter_value": "pink",
                "count_rest": 130,
                "count_recent": 29,
                "recent_family_base": 39,
                "rest_family_base": 171,
                "pct_recent": 0.7435897436,
                "pct_rest": 0.7602339181,
                "delta": -0.0166441745,
            },
            {
                "filter_family": "finish",
                "filter_value": "matte",
                "count_rest": 105,
                "count_recent": 20,
                "recent_family_base": 43,
                "rest_family_base": 174,
                "pct_recent": 0.4651162791,
                "pct_rest": 0.6034482759,
                "delta": -0.1383319968,
            },
            {
                "filter_family": "form",
                "filter_value": "stick",
                "count_rest": 99,
                "count_recent": 24,
                "recent_family_base": 43,
                "rest_family_base": 174,
                "pct_recent": 0.5581395349,
                "pct_rest": 0.5689655172,
                "delta": -0.0108259824,
            },
        ],
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "color lips",
                "attribute_value": "pink",
                "count_top_seller": 0,
                "count_other": 8,
                "top_seller_base": 43,
                "other_base": 167,
                "pct_top_seller": 0.0,
                "pct_other": 0.0479041916,
                "delta": -0.0479041916,
            },
            {
                "attribute_name": "form",
                "attribute_value": "stick",
                "count_top_seller": 10,
                "count_other": 50,
                "top_seller_base": 45,
                "other_base": 172,
                "pct_top_seller": 0.2222222222,
                "pct_other": 0.2906976744,
                "delta": -0.0684754522,
            },
        ],
    )
    _write_csv(
        package_dir / "resolved_core_comparison.csv",
        [
            {
                "attribute_name": "resolved_finish",
                "attribute_value": "matte",
                "count_recent": 17,
                "count_rest": 79,
                "recent_base": 43,
                "rest_base": 174,
                "pct_recent": 0.3953488372,
                "pct_rest": 0.4540229885,
                "delta": -0.0586741513,
            }
        ],
    )

    frames = validator.load_launch_package_data(package_dir).frames

    pink_candidate = validator._best_stability_candidate("pink", frames)
    stick_candidate = validator._best_stability_candidate("stick form", frames)
    matte_candidate = validator._best_stability_candidate("matte finish", frames)

    assert pink_candidate is not None
    assert pink_candidate["file"] == "filter_comparison.csv"
    assert pink_candidate["label"] == "pink"
    assert stick_candidate is not None
    assert stick_candidate["file"] == "filter_comparison.csv"
    assert stick_candidate["label"] == "stick"
    assert matte_candidate is not None
    assert matte_candidate["file"] == "filter_comparison.csv"
    assert matte_candidate["label"] == "matte"


def test_validate_divergence_summary_segment_resolves_duplicate_innovation_pair_rows(
    tmp_path: Path,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "benefits",
                "attribute_value": "hydrating/moisturizing",
                "count_top_seller": 14,
                "count_other": 91,
                "top_seller_base": 43,
                "other_base": 155,
                "pct_top_seller": 0.3255813953,
                "pct_other": 0.5870967742,
                "delta": -0.2615153789,
            }
        ],
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "hydrating/moisturizing + twist-up/retractable",
                "count_recent": 7,
                "count_rest": 0,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0,
                "recent_brand_count": 7,
            },
            {
                "bundle_label": "hydrating moisturizing + twist-up/retractable",
                "count_recent": 7,
                "count_rest": 0,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.1555555556,
                "pct_rest": 0.0,
                "recent_brand_count": 7,
            },
        ],
    )
    _write_csv(
        package_dir / "innovation_triples.csv",
        [
            {
                "bundle_label": "hydrating/moisturizing + twist-up/retractable + long-wear",
                "count_recent": 3,
                "count_rest": 9,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.0666666667,
                "pct_rest": 0.0511363636,
                "recent_brand_count": 3,
            }
        ],
    )

    frames = validator.load_launch_package_data(package_dir).frames
    result = validator._validate_divergence_summary_segment(
        (
            "The divergence: The primary difference between current winners and "
            "recent launches is the stronger, more explicit pairing of hydration "
            "language with retractable-stick packaging."
        ),
        frames,
    )

    assert result is not None
    assert result["status"] == "pass"
    assert result["row_support"]
    assert result["row_support"][0]["source_file"] == "innovation_pairs.csv"
    assert result["row_support"][0]["zero_occurrence_check"][0]["passed"] is True


def test_validate_launch_report_pdf_partially_backs_mixed_attribute_share_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "benefits",
                "attribute_value": "hydrating/moisturizing",
                "count_top_seller": 14,
                "count_other": 91,
                "top_seller_base": 43,
                "other_base": 155,
                "pct_top_seller": 0.3255813953,
                "pct_other": 0.5870967742,
                "delta": -0.2615153789,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-13",
                    "slide_number": 13,
                    "page_number": 13,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "share-1",
                            "type": "text",
                            "text": (
                                "Explicit Hydrating Language (Overall) | "
                                "58.7% (Others) | 42.0% (Top Sellers)"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["partially_backed_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "partially_backed"
    assert claim["claim_family"] == "attribute_share"
    assert claim["details"]["reasons"] == [
        "top_seller percent mismatch: expected 32.6%"
    ]
    assert claim["details"]["matched_metrics"] == ["other_percent"]
    assert claim["details"]["mismatched_metrics"] == ["top_seller_percent"]


def test_validate_launch_report_pdf_partially_backs_attribute_share_role_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "benefits",
                "attribute_value": "Glow-enhancing",
                "count_top_seller": 5,
                "top_seller_base": 33,
                "count_other": 67,
                "other_base": 138,
                "pct_top_seller": 0.1515151515,
                "pct_other": 0.4855072464,
            }
        ],
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "bronzer",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "attribute-share-1",
                            "type": "text",
                            "text": (
                                "Glow-enhancing claims are substantially lower in "
                                "top sellers (17.6%) compared to the rest of the "
                                "market (48.6%)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = payload["claims"][0]
    assert claim["status"] == "partially_backed"
    assert claim["claim_family"] == "attribute_share"
    assert claim["details"]["matched_metrics"] == ["other_percent"]
    assert claim["details"]["mismatched_metrics"] == ["top_seller_percent"]
    assert claim["details"]["reasons"] == [
        "top_seller percent mismatch: expected 15.2%"
    ]
    diagnostics = claim["details"]["numeric_basis_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["role"] == "top_seller"
    assert diagnostics[0]["observed_percent"] == 17.6
    assert diagnostics[0]["expected_percent"] == pytest.approx(15.15151515)
    assert diagnostics[0]["current_count"] == 5
    assert diagnostics[0]["current_base"] == 33
    assert diagnostics[0]["implied_base_if_current_count_held"] == 28
    assert diagnostics[0]["implied_count_if_current_base_held"] == 6


def test_validate_launch_report_pdf_verifies_recent_core_biggest_lift_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "resolved_core_comparison.csv",
        [
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "buildable coverage",
                "count_recent": 11,
                "count_rest": 19,
                "recent_base": 31,
                "rest_base": 152,
                "pct_recent": 0.3548387097,
                "pct_rest": 0.125,
                "delta": 0.2298387097,
            },
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "sheer coverage",
                "count_recent": 5,
                "count_rest": 13,
                "recent_base": 31,
                "rest_base": 152,
                "pct_recent": 0.1612903226,
                "pct_rest": 0.0855263158,
                "delta": 0.0757640068,
            },
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "rank-1",
                            "type": "text",
                            "text": (
                                "Resolved buildable coverage marks the single "
                                "biggest statistical lift in the recent core comparison."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "attribute_rank"
    assert claim["entity"] == "buildable coverage"
    assert claim["file"] == "resolved_core_comparison.csv"
    assert claim["details"]["rank_basis_or_share_basis"]["claim_rank"] == 1
    assert claim["details"]["expected_numeric_values"]["delta"] == 0.2298387097
    assert claim["details"]["denominators"] == {"recent": 31, "rest": 152}


def test_validate_launch_report_pdf_contradicts_wrong_recent_core_biggest_lift_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "resolved_core_comparison.csv",
        [
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "buildable coverage",
                "count_recent": 11,
                "count_rest": 19,
                "recent_base": 31,
                "rest_base": 152,
                "pct_recent": 0.3548387097,
                "pct_rest": 0.125,
                "delta": 0.2298387097,
            },
            {
                "attribute_name": "resolved_coverage",
                "attribute_value": "sheer coverage",
                "count_recent": 5,
                "count_rest": 13,
                "recent_base": 31,
                "rest_base": 152,
                "pct_recent": 0.1612903226,
                "pct_rest": 0.0855263158,
                "delta": 0.0757640068,
            },
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-11",
                    "slide_number": 11,
                    "page_number": 11,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "rank-1",
                            "type": "text",
                            "text": (
                                "Resolved sheer coverage marks the single biggest "
                                "statistical lift in the recent core comparison."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "attribute_rank"
    assert claim["entity"] == "sheer coverage"
    assert claim["details"]["rank_basis_or_share_basis"]["claim_rank"] == 2
    assert claim["details"]["top_ranked_row"] == {
        "attribute_name": "resolved_coverage",
        "attribute_value": "buildable coverage",
    }
    assert claim["details"]["reasons"] == [
        "attribute is not the top-ranked delta in recent core comparison: rank 2"
    ]


def test_validate_launch_report_pdf_classifies_structural_non_claims_and_mapping_issues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-1",
                            "type": "title",
                            "text": "Analytical Recap",
                        },
                        {
                            "block_id": "purpose-1",
                            "type": "bullet_item",
                            "items": [
                                (
                                    "Identifies the stable category grammar and "
                                    "the dominant shade/performance bundles winning by volume."
                                )
                            ],
                        },
                        {
                            "block_id": "setup-1",
                            "type": "paragraph",
                            "text": (
                                "Target: Pareto: Top Sellers vs. Total Category "
                                "Methodology: Attribute mapping and rank-weighted "
                                "visibility Status: Cleared Findings"
                            ),
                        },
                        {
                            "block_id": "group-label-1",
                            "type": "bullet_item",
                            "items": ["Emerging Branch Stick + Hydrating Hybrids"],
                        },
                        {
                            "block_id": "table-title-1",
                            "type": "table_title",
                            "text": "Shade Bundles (Top Sellers vs. Others)",
                        },
                        {
                            "block_id": "matrix-cell-1",
                            "type": "table_title",
                            "text": "11% (Rest)",
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["claim_count"] == 0
    assert payload["summary"]["unresolved_count"] == 0
    assert payload["summary"]["non_claim_count"] == 5
    assert payload["summary"]["mapping_issue_count"] == 1
    assert {item["details"]["filter_rule_id"] for item in payload["non_claims"]} == {
        "NF01",
        "NF02",
        "NF03",
        "NF06",
        "NF07",
    }
    mapping_issue = payload["mapping_issues"][0]
    assert mapping_issue["status"] == "ocr_layout_mapping_issue"
    assert (
        mapping_issue["details"]["mapping_issue_type"]
        == "matrix_row_fragmentation_and_cell_order_scramble"
    )


def test_validate_launch_report_pdf_routes_pro_audited_parser_residuals(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low top sneakers",
        retailer="saksfifthavenue",
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "objective-1",
                            "type": "body_text",
                            "text": (
                                "An objective evaluation of current winning bundles, "
                                "visibility distribution, and promotional dynamics."
                            ),
                        },
                        {
                            "block_id": "exhibit-1",
                            "type": "exhibit_label",
                            "text": "Exhibit D: Top seller / Recent / Unexposed to sale pressure.",
                        },
                        {
                            "block_id": "metric-cell-1",
                            "type": "body_text",
                            "text": "Incremental Visibility: 10.7%",
                        },
                        {
                            "block_id": "ocr-fused-1",
                            "type": "body_text",
                            "text": (
                                "The technical/mesh signal al existsbroadly across "
                                "brands but r remains thinner in 1 total volume than "
                                "the baseline."
                            ),
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": "The emerging layer is not a separate innovation story.",
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["claim_count"] == 0
    assert payload["summary"]["non_claim_count"] == 2
    assert payload["summary"]["mapping_issue_count"] == 2
    assert payload["summary"]["unresolved_count"] == 1
    assert {item["details"]["filter_rule_id"] for item in payload["non_claims"]} == {
        "NF10",
        "NF11",
    }
    assert {
        item["details"]["mapping_issue_type"] for item in payload["mapping_issues"]
    } == {
        "matrix_metric_cell_without_row_label",
        "ocr_fused_or_stray_token_text",
    }
    unresolved = payload["unresolved"][0]
    assert unresolved["claim_family"] == "summary_synthesis"
    assert unresolved["details"]["message"] == (
        "winning summary has no verified deterministic support components yet"
    )


def test_validate_launch_report_pdf_marks_domain_residual_claims_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "chewy",
        category_key="wet_cat_food",
        category_label="wet cat food",
        retailer="chewy",
    )
    pdf_path = tmp_path / "wet_cat_food.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "wet_cat_food",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "residual-1",
                            "type": "body_text",
                            "text": (
                                "The actual drivers of shelf success are "
                                "specific texture formats."
                            ),
                        },
                        {
                            "block_id": "residual-2",
                            "type": "body_text",
                            "text": (
                                "New arrivals overwhelmingly duplicate the "
                                "attributes of existing top-sellers."
                            ),
                        },
                        {
                            "block_id": "meta-1",
                            "type": "body_text",
                            "text": (
                                "Confidence & Limits: Findings carry a Medium "
                                "confidence level."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["unresolved_count"] == 2
    assert payload["summary"]["non_claim_count"] == 1
    assert {item["claim_family"] for item in payload["unresolved"]} == {
        "summary_synthesis",
    }
    assert {item["claim_text"] for item in payload["unresolved"]} == {
        "The actual drivers of shelf success are specific texture formats.",
        "New arrivals overwhelmingly duplicate the attributes of existing top-sellers.",
    }
    assert payload["non_claims"][0]["details"]["filter_rule_id"] == "NF17"


def test_validate_launch_report_pdf_explains_unanchored_rank_delta(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="cashmere_sweaters",
        category_label="cashmere sweaters",
        retailer="saksfifthavenue",
    )
    pdf_path = tmp_path / "cashmere_sweaters.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "cashmere_sweaters",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-10",
                    "slide_number": 10,
                    "page_number": 10,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "rank-delta-1",
                            "type": "bullet_item",
                            "text": (
                                "Negative mean signed delta (-5.7). Represents "
                                "a newness-skewed edge, but lacks recurrent "
                                "bundle strength."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    unresolved = payload["unresolved"][0]
    assert unresolved["claim_family"] == "rank_delta_context_missing"
    assert unresolved["details"]["aggregation_rule_id"] == (
        "rank_delta_anchor_required_v1"
    )
    assert unresolved["details"]["observed_values"]["signed_rank_delta"] == [-5.7]


def test_validate_launch_report_pdf_verifies_low_count_novelty_formats(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "form_children",
                "attribute_value": "balm",
                "count_recent": 4,
                "count_rest": 16,
                "recent_base": 48,
                "rest_base": 191,
                "pct_recent": 0.0833,
                "pct_rest": 0.0838,
                "delta": -0.0005,
            },
            {
                "attribute_name": "form_children",
                "attribute_value": "tint/stain",
                "count_recent": 0,
                "count_rest": 15,
                "recent_base": 48,
                "rest_base": 191,
                "pct_recent": 0.0,
                "pct_rest": 0.0785,
                "delta": -0.0785,
            },
        ],
    )
    product_rows = [
        {
            "parent_product_id": f"recent-{index}",
            "product_name": f"Recent Blush {index}",
            "brand": "Brand",
            "listing_status": "recent",
            "form": "stick",
            "finish": "natural",
        }
        for index in range(1, 12)
    ]
    product_rows[0]["product_name"] = "Sheer High-Shine Blush"
    product_rows[0]["finish"] = "sheer | high shine"
    _write_csv(package_dir / "product_filter_matrix.csv", product_rows)
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "low-count-1",
                            "type": "bullet_item",
                            "text": (
                                "Small-format novelty lacks mass: Balm, stain, "
                                "and sheer/high-shine formats possess product "
                                "counts too low to indicate broad category shifts."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "low_count_novelty"
    assert claim["details"]["aggregation_rule_id"] == "low_count_novelty_format_v1"
    assert payload["summary"]["unresolved_count"] == 0


def test_validate_launch_report_pdf_resolves_current_top_seller_architecture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low-top sneakers",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "lace-up + white + leather + rubber sole + designer/luxury",
                "count_top_seller": 24,
                "count_other": 5,
                "top_seller_brand_count": 8,
                "other_brand_count": 4,
                "top_seller_base": 42,
                "other_base": 165,
                "pct_top_seller": 0.5714,
                "pct_other": 0.0303,
                "delta": 0.5411,
                "prevalence_ratio": 18.86,
            }
        ],
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-2",
                    "slide_number": 2,
                    "page_number": 2,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "architecture-1",
                            "type": "body_text",
                            "text": (
                                "The current top-seller architecture is heavily "
                                "concentrated in white, lace-up, leather or "
                                "rubber-soled luxury low-tops with visible branding."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = payload["claims"][0]
    assert claim["claim_family"] == "summary_synthesis"
    assert claim["status"] in {"verified", "partially_backed"}
    assert claim["details"]["aggregation_rule_id"] == "current_winner_format_summary_v1"
    assert payload["summary"]["unresolved_count"] == 0


def test_validate_launch_report_pdf_uses_exhibit_labels_for_innovation_examples(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low-top sneakers",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "blue + mesh",
                "count_recent": 4,
                "count_rest": 4,
                "recent_brand_count": 3,
                "recent_base": 42,
                "rest_base": 165,
                "pct_recent": 0.0952,
                "pct_rest": 0.0242,
                "delta": 0.071,
                "prevalence_ratio": 3.93,
                "insight_adjusted_signal_score": 12.0,
            },
            {
                "bundle_label": "multicolor + runner-inspired",
                "count_recent": 6,
                "count_rest": 7,
                "recent_brand_count": 4,
                "recent_base": 42,
                "rest_base": 165,
                "pct_recent": 0.1429,
                "pct_rest": 0.0424,
                "delta": 0.1005,
                "prevalence_ratio": 3.37,
                "insight_adjusted_signal_score": 15.0,
            },
            {
                "bundle_label": "white + rubber sole",
                "count_recent": 21,
                "count_rest": 26,
                "recent_brand_count": 10,
                "recent_base": 42,
                "rest_base": 165,
                "pct_recent": 0.5,
                "pct_rest": 0.1576,
                "delta": 0.3424,
                "prevalence_ratio": 3.17,
                "insight_adjusted_signal_score": 20.0,
            },
        ],
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-1",
                            "type": "body_text",
                            "text": "Technical Signal Representation",
                        },
                        {
                            "block_id": "exhibit-i",
                            "type": "exhibit_label",
                            "text": "Exhibit I: Technical mesh construction",
                        },
                        {
                            "block_id": "summary-1",
                            "type": "body_text",
                            "text": (
                                "These items represent high-visibility innovation "
                                "examples within the category."
                            ),
                        },
                        {
                            "block_id": "exhibit-j",
                            "type": "exhibit_label",
                            "text": "Exhibit J: Runner-inspired silhouette",
                        },
                        {
                            "block_id": "exhibit-k",
                            "type": "exhibit_label",
                            "text": "Exhibit K: Technical tooling and sole",
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = payload["claims"][0]
    assert claim["claim_family"] == "summary_synthesis"
    assert claim["status"] == "partially_backed"
    assert claim["details"]["aggregation_rule_id"] == (
        "innovation_exhibit_example_support_v1"
    )
    assert payload["summary"]["unresolved_count"] == 0


def test_iter_slide_units_prefers_clean_banner_text_over_fragments() -> None:
    slide = {
        "slideId": "slide-2",
        "slideNumber": 2,
        "pageNumber": 2,
        "blocks": [
            {
                "blockId": "banner-1",
                "type": "callout_banner",
                "text": (
                    "The category is anchored by a stable core, with modest "
                    "innovation around format."
                ),
                "items": [
                    "The",
                    "category",
                    "is",
                    "anchored",
                    "by",
                    "a",
                    "stable",
                    "core,",
                ],
            }
        ],
    }

    units = validator._iter_slide_units(slide)

    assert len(units) == 1
    assert units[0]["source_kind"] == "block_text"
    assert units[0]["block_type"] == "callout_banner"
    assert units[0]["text"].startswith("The category is anchored")


def test_validate_launch_report_pdf_classifies_labels_fragments_and_ocr_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low top sneakers",
        retailer="saksfifthavenue",
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "product-label",
                            "type": "body_text",
                            "text": (
                                "Product: Example Sneaker Mapped Attributes: "
                                "white + lace-up + leather"
                            ),
                        },
                        {
                            "block_id": "exhibit-label",
                            "type": "body_text",
                            "text": "Exhibit C: Exaggerated rubber sole",
                        },
                        {
                            "block_id": "list-fragment",
                            "type": "bullet_item",
                            "items": ["- Colorblock and slip-on configurations."],
                        },
                        {
                            "block_id": "visual-reference",
                            "type": "body_text",
                            "text": "Images reinforce the data read.",
                        },
                        {
                            "block_id": "ocr-artifact",
                            "type": "body_text",
                            "text": (
                                "Core attributes: white base, lace-up 2069420547 "
                                "closure, leather upper, rubber sole."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["non_claim_count"] == 4
    assert payload["summary"]["mapping_issue_count"] == 1
    assert {item["details"]["filter_rule_id"] for item in payload["non_claims"]} == {
        "NF12",
        "NF13",
        "NF14",
        "NF15",
    }
    assert (
        payload["mapping_issues"][0]["details"]["mapping_issue_type"]
        == "ocr_fused_or_stray_token_text"
    )


def test_iter_slide_units_reconstructs_grouped_table_title_rows() -> None:
    slide = {
        "slideId": "slide-9",
        "slideNumber": 9,
        "pageNumber": 9,
        "blocks": [
            {
                "blockId": "header-1",
                "type": "table_title",
                "text": "Attribute Bundle",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 80, "y": 120, "w": 180, "h": 22},
            },
            {
                "blockId": "header-2",
                "type": "table_title",
                "text": "Recent (%)",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 410, "y": 120, "w": 100, "h": 22},
            },
            {
                "blockId": "header-3",
                "type": "table_title",
                "text": "Rest (%)",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 600, "y": 120, "w": 90, "h": 22},
            },
            {
                "blockId": "row-1-label",
                "type": "table_title",
                "text": "Red + High Shine",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 82, "y": 178, "w": 210, "h": 24},
            },
            {
                "blockId": "row-1-recent",
                "type": "table_title",
                "text": "24% (11 products)",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 414, "y": 180, "w": 118, "h": 24},
            },
            {
                "blockId": "row-1-rest",
                "type": "table_title",
                "text": "11% (Rest)",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 608, "y": 179, "w": 102, "h": 24},
            },
            {
                "blockId": "row-2-label",
                "type": "table_title",
                "text": "Wine + Stick",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 81, "y": 238, "w": 188, "h": 24},
            },
            {
                "blockId": "row-2-recent",
                "type": "table_title",
                "text": "24% (11 products)",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 415, "y": 240, "w": 118, "h": 24},
            },
            {
                "blockId": "row-2-rest",
                "type": "table_title",
                "text": "13% (Rest)",
                "groupId": "group-2",
                "groupKind": "table",
                "bbox": {"x": 609, "y": 239, "w": 102, "h": 24},
            },
        ],
        "figureRegions": [],
    }

    units = validator._iter_slide_units(validator._canonicalize_analysis_slide(slide))

    assert [unit["text"] for unit in units] == [
        "Red + High Shine | 24% (11 products) | 11% (Rest)",
        "Wine + Stick | 24% (11 products) | 13% (Rest)",
    ]
    for unit in units:
        assert unit["source_kind"] == "table_row"
        assert unit["block_id"] == "group-2"
        assert unit["block_type"] == "table"
        assert unit["reconstructed_from_group_table_titles"] is True
        assert len(unit["source_block_ids"]) == 3


def test_validate_launch_report_pdf_reconstructs_slide_nine_rows_before_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "red + high shine",
                "count_recent": 11,
                "count_rest": 20,
                "pct_recent": 0.2444444444,
                "pct_rest": 0.1136363636,
                "recent_brand_count": 9,
                "rest_brand_count": 17,
            },
            {
                "bundle_label": "wine + stick",
                "count_recent": 11,
                "count_rest": 23,
                "pct_recent": 0.2444444444,
                "pct_rest": 0.1306818182,
                "recent_brand_count": 6,
                "rest_brand_count": 16,
            },
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-1",
                            "type": "title",
                            "text": "Emerging Signal 1: Wine and High-Shine Sticks",
                        },
                        {
                            "block_id": "header-1",
                            "type": "table_title",
                            "text": "Attribute Bundle",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 80, "y": 120, "w": 180, "h": 22},
                        },
                        {
                            "block_id": "header-2",
                            "type": "table_title",
                            "text": "Recent (%)",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 410, "y": 120, "w": 100, "h": 22},
                        },
                        {
                            "block_id": "header-3",
                            "type": "table_title",
                            "text": "Rest (%)",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 600, "y": 120, "w": 90, "h": 22},
                        },
                        {
                            "block_id": "row-1-label",
                            "type": "table_title",
                            "text": "Red + High Shine",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 82, "y": 178, "w": 210, "h": 24},
                        },
                        {
                            "block_id": "row-1-recent",
                            "type": "table_title",
                            "text": "24% (11 products)",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 414, "y": 180, "w": 118, "h": 24},
                        },
                        {
                            "block_id": "row-1-rest",
                            "type": "table_title",
                            "text": "11% (Rest)",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 608, "y": 179, "w": 102, "h": 24},
                        },
                        {
                            "block_id": "row-2-label",
                            "type": "table_title",
                            "text": "Wine + Stick",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 81, "y": 238, "w": 188, "h": 24},
                        },
                        {
                            "block_id": "row-2-recent",
                            "type": "table_title",
                            "text": "24% (11 products)",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 415, "y": 240, "w": 118, "h": 24},
                        },
                        {
                            "block_id": "row-2-rest",
                            "type": "table_title",
                            "text": "13% (Rest)",
                            "groupId": "group-2",
                            "groupKind": "table",
                            "bbox": {"x": 609, "y": 239, "w": 102, "h": 24},
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim_texts = {item["claim_text"] for item in payload["claims"]}
    assert "Red + High Shine | 24% (11 products) | 11% (Rest)" in claim_texts
    assert "Wine + Stick | 24% (11 products) | 13% (Rest)" in claim_texts

    bundle_claims = [
        item for item in payload["claims"] if item["claim_family"] == "bundle_metric"
    ]
    assert {item["status"] for item in bundle_claims} == {"verified"}
    assert {item["claim_text"] for item in bundle_claims} == {
        "Red + High Shine | 24% (11 products) | 11% (Rest)",
        "Wine + Stick | 24% (11 products) | 13% (Rest)",
    }

    remaining_texts = {
        item["claim_text"]
        for collection in (
            payload["unresolved"],
            payload["mapping_issues"],
            payload["non_claims"],
        )
        for item in collection
    }
    assert "Red + High Shine" not in remaining_texts
    assert "Wine + Stick" not in remaining_texts
    assert "24% (11 products)" not in remaining_texts
    assert "11% (Rest)" not in remaining_texts
    assert "13% (Rest)" not in remaining_texts


def test_validate_launch_report_pdf_treats_substantive_titles_as_non_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "title-1",
                            "type": "title",
                            "text": "Emerging Signal 1: Wine and High-Shine Sticks",
                        },
                        {
                            "block_id": "body-1",
                            "type": "text",
                            "text": (
                                "The innovation layer reveals a modest emerging signal "
                                "splitting into two adjacent lanes rather than a category reset."
                            ),
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["non_claim_count"] == 1
    assert payload["summary"]["unresolved_count"] == 1
    title_item = payload["non_claims"][0]
    assert title_item["block_type"] == "title"
    assert title_item["claim_text"] == "Emerging Signal 1: Wine and High-Shine Sticks"
    assert title_item["details"]["filter_rule_id"] == "NF01"
    assert title_item["details"]["filter_reason"] == (
        "slide title is structural and out of claim scope"
    )
    assert payload["unresolved"][0]["claim_text"].startswith(
        "The innovation layer reveals a modest emerging signal"
    )


def test_validate_launch_report_pdf_requires_meaningful_attribute_label_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "product_name_norm",
                "attribute_value": "I'm Blushing 2-in-1 Cheek and Lip Tint",
                "count_top_seller": 0,
                "count_other": 1,
                "top_seller_base": 68,
                "other_base": 271,
                "pct_top_seller": 0.0,
                "pct_other": 0.0036900369,
            }
        ],
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    bridge_text = (
        "The most credible bridge between current winners (19.6% vs 14.0%) "
        "and emerging releases (27.7% vs 12.2%)."
    )
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "blush",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-8",
                    "slide_number": 8,
                    "page_number": 8,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bridge-1",
                            "type": "text",
                            "text": bridge_text,
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["summary"]["contradicted_count"] == 0
    assert not any(
        item["claim_family"] == "attribute_share" for item in payload["claims"]
    )
    assert payload["summary"]["unresolved_count"] == 1
    assert payload["unresolved"][0]["claim_text"] == bridge_text


def test_validate_launch_report_pdf_accepts_approximate_recent_rest_bundle_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lipstick",
        category_label="lipstick",
    )
    _write_csv(package_dir / "top_seller_pairs.csv", [])
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "red + stick",
                "count_recent": 18,
                "count_rest": 69,
                "recent_base": 45,
                "rest_base": 176,
                "pct_recent": 0.4,
                "pct_rest": 0.3920454545,
            }
        ],
    )
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lipstick",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "Red + stick form: Recent (%) 40.0% (Recent); "
                                "Rest (%) ~39.0% (Rest)"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["file"] == "innovation_pairs.csv"


def test_validate_launch_report_pdf_marks_subset_base_wording_as_partially_backed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_balm",
        category_label="lip balm",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "ethical/regulatory claims",
                "attribute_value": "vegan",
                "count_top_seller": 33,
                "count_other": 99,
                "top_seller_base": 59,
                "other_base": 198,
                "pct_top_seller": 0.5593220339,
                "pct_other": 0.5,
                "delta": 0.0593220339,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "color=clear + form=balm",
                "bundle_label": "clear + balm",
                "count_top_seller": 49,
                "count_other": 82,
                "top_seller_brand_count": 38,
                "other_brand_count": 61,
                "top_seller_base": 78,
                "other_base": 309,
                "pct_top_seller": 0.6282051282,
                "pct_other": 0.2653721683,
                "delta": 0.3628329599,
                "prevalence_ratio": 2.3672607880,
            }
        ],
    )

    pdf_path = tmp_path / "lip_balm.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_balm",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-4",
                    "slide_number": 4,
                    "page_number": 4,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": "Vegan attributes appear in 55.9% of top sellers versus 50.0% of others.",
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["contradicted_count"] == 0
    assert payload["summary"]["partially_backed_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "partially_backed"
    assert claim["claim_family"] == "attribute_share"
    assert "subset-based" in claim["details"]["reasons"][0]
    assert claim["details"]["package_values"]["top_seller_base"] == 59
    assert claim["details"]["package_values"]["other_base"] == 198
    assert claim["details"]["population_scope"]["status"] == "partially_backed"


def test_validate_launch_report_pdf_requires_primary_metric_for_partial_bundle_support(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saksfifthavenue",
        category_key="low_top_sneakers",
        category_label="low-top sneakers",
        retailer="saksfifthavenue",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "closure=lace-up + material=mesh",
                "bundle_label": "lace-up + mesh",
                "count_recent": 5,
                "count_rest": 15,
                "recent_brand_count": 4,
                "rest_brand_count": 12,
                "recent_base": 42,
                "rest_base": 165,
                "pct_recent": 0.1190476190,
                "pct_rest": 0.0909090909,
                "delta": 0.0281385281,
                "prevalence_ratio": 1.3095,
            }
        ],
    )
    pdf_path = tmp_path / "low_top_sneakers.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "low_top_sneakers",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-7",
                    "slide_number": 7,
                    "page_number": 7,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "bundle-1",
                            "type": "text",
                            "text": (
                                "lace-up + mesh: Recent Penetration 19.4%; "
                                "Rest Penetration 8.3%; Difference +11.1 pp; "
                                "Brand Breadth 12 brands"
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["details"]["matched_metrics"] == ["brand_count"]
    assert set(claim["details"]["mismatched_metrics"]) == {
        "recent_percent",
        "rest_percent",
        "delta_pct_points",
    }


def test_validate_launch_report_pdf_flags_qualified_subset_denominator_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_balm",
        category_label="lip balm",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_size": 2,
                "bundle_key": "coverage=sheer coverage + scent/flavor=fruity",
                "bundle_label": "sheer coverage + fruity",
                "count_recent": 15,
                "count_rest": 33,
                "recent_brand_count": 11,
                "rest_brand_count": 24,
                "recent_base": 78,
                "rest_base": 309,
                "pct_recent": 0.1923076923,
                "pct_rest": 0.1067961165,
                "delta": 0.0855115758,
                "prevalence_ratio": 1.8006993007,
            }
        ],
    )

    pdf_path = tmp_path / "lip_balm.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_balm",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-9",
                    "slide_number": 9,
                    "page_number": 9,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-4",
                            "type": "group_label",
                            "text": "Fruity/Playful Expression",
                            "items": ["Fruity/Playful Expression"],
                            "groupId": "g1",
                        },
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": "Appears in 19.2% of recent sheer products vs 10.7% of rest.",
                            "parentId": "block-4",
                            "groupId": "g1",
                        },
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    assert payload["summary"]["contradicted_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["entity"] == "sheer coverage + fruity"
    assert "qualified denominator wording" in claim["details"]["reasons"][0]
    assert claim["details"]["package_values"]["recent_base"] == 78
    assert claim["details"]["package_values"]["rest_base"] == 309


def test_validate_launch_report_pdf_matches_camel_case_bundle_labels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "saloncentric",
        category_key="permanent",
        category_label="permanent hair color",
        retailer="saloncentric",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_key": "product benefit=greyCoverage + product form=cream",
                "bundle_label": "greyCoverage + cream",
                "count_top_seller": 10,
                "count_other": 21,
                "top_seller_base": 18,
                "other_base": 68,
                "pct_top_seller": 0.5555555556,
                "pct_other": 0.3088235294,
                "top_seller_brand_count": 8,
            }
        ],
    )

    pdf_path = tmp_path / "permanent_saloncentric.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "permanent_saloncentric",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": (
                                "Grey Coverage + Cream: 55.6% of top sellers "
                                "(across 8 brands) vs 30.9% of others."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    assert payload["summary"]["contradicted_count"] == 0
    assert payload["claims"][0]["entity"] == "greyCoverage + cream"


def test_validate_launch_report_pdf_handles_candidate_with_missing_percent_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_oil",
        category_label="lip oil",
    )
    _write_csv(
        package_dir / "filter_comparison.csv",
        [
            {
                "filter_family": "coverage",
                "filter_value": "buildable",
                "count_rest": 2,
                "count_recent": 0,
                "recent_family_base": None,
                "rest_family_base": 2,
                "pct_recent": None,
                "pct_rest": 1.0,
                "delta": None,
            }
        ],
    )

    pdf_path = tmp_path / "lip_oil.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_oil",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-1",
                    "slide_number": 1,
                    "page_number": 1,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": "Buildable: Recent (%) 0%; Rest (%) 100%",
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["contradicted_count"] == 0
    assert payload["summary"]["unresolved_count"] == 1
    claim = payload["unresolved"][0]
    assert claim["status"] == "unresolved"
    assert claim["claim_family"] == "bundle_metric"
    candidate = claim["details"]["candidate_evaluations"][0]
    assert candidate["file"] == "filter_comparison.csv"
    assert candidate["reasons"]


def test_validate_launch_report_pdf_resolves_symmetric_bundle_rest_only_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_treatment",
        category_label="lip treatment",
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "vegan + hydration",
                "count_recent": 12,
                "count_rest": 12,
                "recent_base": 38,
                "rest_base": 150,
                "pct_recent": 0.3157894737,
                "pct_rest": 0.08,
            },
            {
                "bundle_label": "hydration + vegan",
                "count_recent": 13,
                "count_rest": 12,
                "recent_base": 38,
                "rest_base": 150,
                "pct_recent": 0.3421052632,
                "pct_rest": 0.08,
            },
        ],
    )

    pdf_path = tmp_path / "lip_treatment.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_treatment",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-6",
                    "slide_number": 6,
                    "page_number": 6,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": (
                                "Feature explicit hydration paired with vegan "
                                "language (vs. 8.0% of the rest)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    assert payload["summary"]["unresolved_count"] == 0
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["file"] == "innovation_pairs.csv"


def test_validate_launch_report_pdf_does_not_contradict_ocr_fused_partial_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_treatment",
        category_label="lip treatment",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "treatment benefits",
                "attribute_value": "repair",
                "count_top_seller": 7,
                "count_other": 16,
                "top_seller_base": 24,
                "other_base": 90,
                "pct_top_seller": 0.2916666667,
                "pct_other": 0.1777777778,
            }
        ],
    )

    pdf_path = tmp_path / "lip_treatment.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_treatment",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": 'Atightervariantadding"repair"claims captures 13.2% of top sellers.',
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["contradicted_count"] == 0
    assert payload["unresolved"][0]["claim_family"] == "bundle_metric"
    assert (
        payload["unresolved"][0]["details"]["message"]
        == "bundle metric could not be cleanly disambiguated"
    )


def test_validate_launch_report_pdf_resolves_repair_variant_with_specific_bundle_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_treatment",
        category_label="lip treatment",
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "treatment benefits",
                "attribute_value": "repair",
                "count_top_seller": 7,
                "count_other": 16,
                "top_seller_base": 24,
                "other_base": 90,
                "pct_top_seller": 0.2916666667,
                "pct_other": 0.1777777778,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "unscented + repair",
                "count_top_seller": 5,
                "count_other": 8,
                "top_seller_base": 38,
                "other_base": 150,
                "pct_top_seller": 0.1315789474,
                "pct_other": 0.0533333333,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "balm + unscented + repair",
                "count_top_seller": 5,
                "count_other": 8,
                "top_seller_base": 38,
                "other_base": 150,
                "pct_top_seller": 0.1315789474,
                "pct_other": 0.0533333333,
            }
        ],
    )

    pdf_path = tmp_path / "lip_treatment.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_treatment",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": (
                                'A tighter variant adding "repair" claims captures '
                                "13.2% of top sellers."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    assert payload["summary"]["contradicted_count"] == 0
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["file"] == "top_seller_triples.csv"


def test_validate_launch_report_pdf_matches_slash_synonym_bundle_part(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="lip_treatment",
        category_label="lip treatment",
    )
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "hydrating + balm",
                "count_top_seller": 18,
                "count_other": 47,
                "top_seller_base": 38,
                "other_base": 150,
                "pct_top_seller": 0.4736842105,
                "pct_other": 0.3133333333,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "hydrating + glossy/high-shine + balm",
                "count_top_seller": 9,
                "count_other": 9,
                "top_seller_base": 38,
                "other_base": 150,
                "pct_top_seller": 0.2368421053,
                "pct_other": 0.06,
            }
        ],
    )

    pdf_path = tmp_path / "lip_treatment.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: {
            "deck_id": "lip_treatment",
            "lang": "eng",
            "slides": [
                {
                    "slide_id": "slide-3",
                    "slide_number": 3,
                    "page_number": 3,
                    "ocr_text": "",
                    "blocks": [
                        {
                            "block_id": "block-1",
                            "type": "text",
                            "text": (
                                "The strongest sub-expression is hydrating + glossy "
                                "+ balm (23.7% of top sellers)."
                            ),
                        }
                    ],
                    "figure_regions": [],
                }
            ],
        },
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    assert payload["summary"]["verified_count"] == 1
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "bundle_metric"
    assert claim["file"] == "top_seller_triples.csv"


def _price_comparison_reading_payload(text: str) -> dict[str, object]:
    return {
        "deck_id": "bronzer",
        "lang": "eng",
        "slides": [
            {
                "slide_id": "slide-8",
                "slide_number": 8,
                "page_number": 8,
                "ocr_text": text,
                "blocks": [
                    {
                        "block_id": "block-1",
                        "type": "text",
                        "text": text,
                    }
                ],
                "figure_regions": [],
            }
        ],
    }


def test_validate_launch_report_pdf_checks_entry_price_median_comparison(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="bronzer",
        category_label="bronzer",
    )
    _write_csv(
        package_dir / "recent_products.csv",
        [
            {"parent_product_id": "recent-1", "entry_price": 25.0},
            {"parent_product_id": "recent-2", "entry_price": 30.0},
            {"parent_product_id": "recent-3", "entry_price": 35.0},
        ],
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {"parent_product_id": "recent-1", "entry_price": 25.0},
            {"parent_product_id": "recent-2", "entry_price": 30.0},
            {"parent_product_id": "recent-3", "entry_price": 35.0},
            {"parent_product_id": "rest-1", "entry_price": 20.0},
            {"parent_product_id": "rest-2", "entry_price": 28.0},
            {"parent_product_id": "rest-3", "entry_price": 40.0},
        ],
    )
    text = (
        "Price: Contextual only. Recent products show a modestly higher entry "
        "price (median $30 vs $28), but price tier does not define the main "
        "attribute signal."
    )
    pdf_path = tmp_path / "bronzer.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: _price_comparison_reading_payload(text),
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "pass"
    claim = payload["claims"][0]
    assert claim["status"] == "verified"
    assert claim["claim_family"] == "entry_price_comparison"
    assert claim["details"]["matched_row_keys"] == {
        "metric": "median",
        "comparison_roles": ["recent", "rest"],
    }
    assert (
        claim["details"]["package_values"]["cohorts"]["recent"]["entry_price_median"]
        == 30.0
    )
    assert (
        claim["details"]["package_values"]["cohorts"]["rest"]["entry_price_median"]
        == 28.0
    )


def test_validate_launch_report_pdf_contradicts_entry_price_mean_comparison(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_launch_package(
        tmp_path / "packages" / "launch" / "ulta",
        category_key="blush",
        category_label="blush",
    )
    _write_csv(
        package_dir / "recent_products.csv",
        [
            {"parent_product_id": "recent-1", "entry_price": 28.0},
            {"parent_product_id": "recent-2", "entry_price": 28.5},
        ],
    )
    _write_csv(
        package_dir / "product_filter_matrix.csv",
        [
            {"parent_product_id": "recent-1", "entry_price": 28.0},
            {"parent_product_id": "recent-2", "entry_price": 28.5},
            {"parent_product_id": "rest-1", "entry_price": 27.0},
            {"parent_product_id": "rest-2", "entry_price": 27.5},
        ],
    )
    text = (
        "Price is statistically paired: Recent and rest products are nearly "
        "identical on average entry price ($28.42 recent vs. $28.60 rest)."
    )
    pdf_path = tmp_path / "blush.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: _price_comparison_reading_payload(text),
    )

    payload = validator.validate_launch_report_pdf(pdf_path, package_dir=package_dir)

    assert payload["status"] == "fail"
    claim = payload["claims"][0]
    assert claim["status"] == "contradicted"
    assert claim["claim_family"] == "entry_price_comparison"
    assert claim["details"]["matched_row_keys"] == {
        "metric": "mean",
        "comparison_roles": ["recent", "rest"],
    }
    assert (
        claim["details"]["package_values"]["cohorts"]["recent"]["entry_price_mean"]
        == 28.25
    )
    assert (
        claim["details"]["package_values"]["cohorts"]["rest"]["entry_price_mean"]
        == 27.25
    )
    assert claim["details"]["reasons"] == [
        "recent mean entry price mismatch: expected $28.25",
        "rest mean entry price mismatch: expected $27.25",
    ]


def test_review_launch_report_validation_with_llm_is_advisory(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_query(
        llm_wrapper: object,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, object]:
        captured["llm_wrapper"] = llm_wrapper
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return {
            "summary": "One unresolved numeric-looking claim should become a helper.",
            "items": [
                {
                    "source": "unresolved",
                    "source_index": 0,
                    "slide_number": 4,
                    "claim_text": "A figure region contains a percentage.",
                    "llm_category": "candidate_numeric_claim",
                    "priority": "high",
                    "recommended_action": "add_deterministic_helper",
                    "rationale": "Numeric text should be checked by code.",
                    "suggested_helper_family": "figure_metric",
                }
            ],
            "missed_claim_candidates": [],
            "helper_suggestions": [
                {
                    "slide_number": 4,
                    "claim_text": "A figure region contains a percentage.",
                    "claim_family": "figure_metric",
                    "recommended_action": "add_deterministic_helper",
                    "rationale": "Need a figure parser before validation.",
                }
            ],
        }

    monkeypatch.setattr(validator, "_query_launch_validation_llm", _fake_query)
    llm_wrapper = object()
    payload = {
        "status": "pass_with_warnings",
        "pdf_path": "/tmp/lip_balm.pdf",
        "summary": {
            "verified_count": 0,
            "contradicted_count": 0,
            "partially_backed_count": 0,
            "weakly_backed_count": 0,
            "unresolved_count": 1,
            "claim_count": 0,
            "slide_count": 1,
        },
        "claims": [],
        "unresolved": [
            {
                "status": "unresolved",
                "claim_family": "figure_region",
                "claim_text": "Image region",
                "slide_number": 4,
                "source_kind": "figure_region",
            }
        ],
    }

    review = validator.review_launch_report_validation_with_llm(
        payload,
        llm_wrapper=llm_wrapper,
        max_items=4,
    )

    assert review["status"] == "reviewed"
    assert review["effect_on_validation_status"] == "none"
    assert review["items"][0]["recommended_action"] == "add_deterministic_helper"
    assert review["helper_suggestions"][0]["claim_family"] == "figure_metric"
    assert captured["llm_wrapper"] is llm_wrapper
    assert "Do not recalculate" in str(captured["system_prompt"])
    assert "candidate_items" in str(captured["user_prompt"])


def test_review_launch_report_validation_with_llm_fails_on_openai_error(
    monkeypatch,
) -> None:
    def _raise_openai_failure(*args, **kwargs):
        raise RuntimeError("connection failed")

    monkeypatch.setattr(
        validator, "_query_launch_validation_llm", _raise_openai_failure
    )
    payload = {
        "status": "pass_with_warnings",
        "pdf_path": "/tmp/lip_balm.pdf",
        "summary": {
            "verified_count": 0,
            "contradicted_count": 0,
            "partially_backed_count": 0,
            "weakly_backed_count": 0,
            "unresolved_count": 1,
            "claim_count": 0,
            "slide_count": 1,
        },
        "claims": [],
        "unresolved": [
            {
                "status": "unresolved",
                "claim_family": "figure_region",
                "claim_text": "A figure region contains a percentage.",
                "slide_number": 4,
                "source_kind": "figure_region",
            }
        ],
    }

    with pytest.raises(
        validator.LaunchValidationOpenAIError,
        match="OpenAI call failed during launch validation LLM review",
    ):
        validator.review_launch_report_validation_with_llm(
            payload,
            llm_wrapper=object(),
            max_items=4,
        )


def test_validate_launch_report_batch_batches_multiple_llm_reviews(
    monkeypatch,
) -> None:
    pdf_paths = [Path("/tmp/lipstick.pdf"), Path("/tmp/lip_balm.pdf")]
    llm_wrapper = object()
    validation_calls: list[dict[str, object]] = []

    def _payload(path: Path) -> dict[str, object]:
        return {
            "status": "pass_with_warnings",
            "pdf_path": str(path),
            "summary": {
                "verified_count": 0,
                "contradicted_count": 0,
                "partially_backed_count": 0,
                "weakly_backed_count": 0,
                "unresolved_count": 1,
                "claim_count": 0,
                "slide_count": 1,
            },
            "claims": [],
            "unresolved": [
                {
                    "status": "unresolved",
                    "claim_family": "unclassified",
                    "claim_text": f"{path.stem} residual claim",
                    "slide_number": 2,
                    "source_kind": "bullet",
                }
            ],
        }

    def _fake_validate(pdf_path: Path, **kwargs: object) -> dict[str, object]:
        validation_calls.append(kwargs)
        return _payload(pdf_path)

    batch_calls: dict[str, object] = {}

    def _fake_run_step_json(
        wrapper: object,
        step: str,
        system_prompt: str,
        prompts: list[str],
    ) -> list[dict[str, object]]:
        batch_calls["wrapper"] = wrapper
        batch_calls["step"] = step
        batch_calls["system_prompt"] = system_prompt
        batch_calls["prompts"] = prompts
        return [
            {
                "summary": f"review {index}",
                "items": [
                    {
                        "source": "unresolved",
                        "source_index": 0,
                        "recommended_action": "add_deterministic_helper",
                        "llm_category": "residual_claim",
                    }
                ],
            }
            for index in range(len(prompts))
        ]

    monkeypatch.setattr(validator, "validate_launch_report_pdf", _fake_validate)
    monkeypatch.setattr("modules.llm.batch_runner.run_step_json", _fake_run_step_json)

    batch = validator.validate_launch_report_batch(
        pdf_paths,
        llm_review=True,
        llm_wrapper=llm_wrapper,
    )

    assert [call["llm_review"] for call in validation_calls] == [False, False]
    assert batch_calls["wrapper"] is llm_wrapper
    assert batch_calls["step"] == get_naming_params()["launchValidationReviewQuery"]
    assert "Do not recalculate" in str(batch_calls["system_prompt"])
    assert len(batch_calls["prompts"]) == 2
    assert batch["reports"][0]["llm_review"]["status"] == "reviewed"
    assert batch["reports"][1]["llm_review"]["items"][0]["llm_category"] == (
        "residual_claim"
    )


def test_validate_launch_report_batch_single_llm_review_uses_live_call(
    monkeypatch,
) -> None:
    pdf_paths = [Path("/tmp/lipstick.pdf"), Path("/tmp/lips.pdf")]
    llm_wrapper = object()

    def _fake_validate(pdf_path: Path, **kwargs: object) -> dict[str, object]:
        unresolved = []
        if pdf_path.stem == "lipstick":
            unresolved = [
                {
                    "status": "unresolved",
                    "claim_family": "unclassified",
                    "claim_text": "one residual claim",
                    "slide_number": 2,
                    "source_kind": "bullet",
                }
            ]
        return {
            "status": "pass_with_warnings",
            "pdf_path": str(pdf_path),
            "summary": {
                "verified_count": 0,
                "contradicted_count": 0,
                "partially_backed_count": 0,
                "weakly_backed_count": 0,
                "unresolved_count": len(unresolved),
                "claim_count": 0,
                "slide_count": 1,
            },
            "claims": [],
            "unresolved": unresolved,
        }

    live_calls: list[tuple[object, str, str]] = []

    def _fake_query(
        wrapper: object,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, object]:
        live_calls.append((wrapper, system_prompt, user_prompt))
        return {"summary": "single live review", "items": []}

    monkeypatch.setattr(validator, "validate_launch_report_pdf", _fake_validate)
    monkeypatch.setattr(validator, "_query_launch_validation_llm", _fake_query)
    monkeypatch.setattr(
        "modules.llm.batch_runner.run_step_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("single review should not use provider batch")
        ),
    )

    batch = validator.validate_launch_report_batch(
        pdf_paths,
        llm_review=True,
        llm_wrapper=llm_wrapper,
    )

    assert len(live_calls) == 1
    assert live_calls[0][0] is llm_wrapper
    assert batch["reports"][0]["llm_review"]["status"] == "reviewed"
    assert batch["reports"][1]["llm_review"]["status"] == "skipped"


def test_build_pdf_ocr_payload_for_validation_aliases_full_reading_builder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    expected = {"deck_id": "lipstick", "slides": []}

    monkeypatch.setattr(
        validator,
        "build_pdf_reading_payload_for_validation",
        lambda *args, **kwargs: expected,
    )

    actual = validator.build_pdf_ocr_payload_for_validation(pdf_path)

    assert actual is expected


def test_build_pdf_reading_payload_for_validation_persists_cache_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    fake_layout_payload = {
        "deckId": "lipstick",
        "lang": "eng",
        "slides": [
            {
                "slideId": "slide-1",
                "slideNumber": 1,
                "pageNumber": 1,
                "assetPath": "assets/fake.png",
                "blocks": [],
                "titleText": "Cached title",
                "bulletTexts": [],
                "figureRegions": [],
            }
        ],
    }
    fake_ocr_payload = {
        "deck_id": "lipstick",
        "lang": "eng",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "ocr_text": "Cached title block",
                "blocks": [],
                "figure_regions": [],
            }
        ],
    }
    fake_analysis = _fake_cached_analysis_payload()

    def _fake_render_pdf_deck(
        deck_id: str,
        deck_path: Path,
        pdf_bytes: bytes,
        storage,
        *,
        prompt_style: str,
        owner_email: str | None,
        shared_with: list[str],
    ) -> None:
        deck_path.mkdir(parents=True, exist_ok=True)
        (deck_path / "source.pdf").write_bytes(pdf_bytes)
        storage.save_deck(
            Deck(
                deck_id=deck_id,
                prompt_style=prompt_style,
                owner_email=owner_email,
                shared_with=shared_with,
                slides=[
                    Slide(
                        id="slide-1",
                        title_html="<h1>Cached title</h1>",
                        body_html="<p>Cached body</p>",
                    )
                ],
            )
        )

    monkeypatch.setattr("modules.slides.api._render_pdf_deck", _fake_render_pdf_deck)
    monkeypatch.setattr(
        "modules.slides.api._normalize_layout_payload",
        lambda payload, *, deck_id, lang: payload,
    )
    monkeypatch.setattr(
        "modules.slides.api._build_slide_analysis_payload",
        lambda layout_payload, ocr_payload, *, deck_id, lang: fake_analysis,
    )
    monkeypatch.setattr(
        "src.slides.layout_service.build_deck_layout_payload",
        lambda deck, deck_path, *, lang, **_kwargs: fake_layout_payload,
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_ocr_payload",
        lambda deck, deck_path, *, lang, include_bboxes, layout_payload, pdf_path, **_kwargs: fake_ocr_payload,
    )

    payload = validator.build_pdf_reading_payload_for_validation(pdf_path)

    assert payload["deck_id"] == "lipstick"
    assert payload["slides"][0]["title_text"] == "Cached title"
    assert payload["slides"][0]["blocks"][0]["confidence"] == 0.91
    assert payload["slides"][0]["blocks"][0]["audit_status"] == "ok"
    assert payload["slides"][0]["blocks"][0]["visual_status"] == "corrected"
    assert payload["slides"][0]["blocks"][0]["visual_confidence"] == 0.94
    assert payload["reading_completeness"]["status"] == "read_ok"
    assert payload["reading_completeness"]["summary"]["ocr_line_count"] == 1
    cache_dir = tmp_path / ".launch_report_reading_cache" / "lipstick"
    assert (cache_dir / "layout.json").exists()
    assert (cache_dir / "ocr.json").exists()
    assert (cache_dir / "slide_analysis.json").exists()
    cache_meta = json.loads(
        (cache_dir / "reading_cache_meta.json").read_text(encoding="utf-8")
    )
    assert cache_meta["pipeline_version"] == validator._READING_CACHE_PIPELINE_VERSION


def test_reading_cache_deck_id_preserves_pdf_stem() -> None:
    assert validator._reading_cache_deck_id(Path("blush_ulta.pdf")) == "blush_ulta"


def test_reading_cache_meta_reuses_unchanged_pdf_across_pipeline_versions(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_bytes = b"%PDF-1.4\n"
    pdf_path.write_bytes(pdf_bytes)
    source_sha256 = validator._pdf_content_sha256(pdf_bytes)

    current_meta = validator._build_reading_cache_meta(
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=source_sha256,
    )

    assert validator._reading_cache_is_current(
        current_meta,
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=source_sha256,
    )

    legacy_meta = dict(current_meta)
    legacy_meta.pop("pipeline_version")
    assert validator._reading_cache_is_current(
        legacy_meta,
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=source_sha256,
    )

    stale_meta = dict(current_meta)
    stale_meta["pipeline_version"] = validator._READING_CACHE_PIPELINE_VERSION - 1
    assert validator._reading_cache_is_current(
        stale_meta,
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=source_sha256,
    )


def test_reading_cache_meta_reuses_unchanged_pdf_when_file_stat_changes(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "bronzer_ulta.pdf"
    pdf_bytes = b"%PDF-1.4 unchanged\n"
    pdf_path.write_bytes(pdf_bytes)
    source_sha256 = validator._pdf_content_sha256(pdf_bytes)
    current_meta = validator._build_reading_cache_meta(
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=source_sha256,
    )
    current_meta["source_size"] = 1
    current_meta["source_mtime_ns"] = 1

    assert validator._reading_cache_is_current(
        current_meta,
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=source_sha256,
    )


def test_reading_cache_meta_requires_source_hash_match(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blush_ulta.pdf"
    original_bytes = b"%PDF-1.4 original\n"
    pdf_path.write_bytes(original_bytes)
    original_hash = validator._pdf_content_sha256(original_bytes)
    current_meta = validator._build_reading_cache_meta(
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=original_hash,
    )

    updated_bytes = b"%PDF-1.4 updated!\n"
    pdf_path.write_bytes(updated_bytes)
    updated_stat = pdf_path.stat()
    current_meta["source_size"] = int(updated_stat.st_size)
    current_meta["source_mtime_ns"] = int(updated_stat.st_mtime_ns)

    assert not validator._reading_cache_is_current(
        current_meta,
        pdf_path,
        lang="eng",
        include_bboxes=True,
        source_sha256=validator._pdf_content_sha256(updated_bytes),
    )


def test_build_pdf_reading_payload_for_validation_reuses_current_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "lipstick.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    fake_layout_payload = {
        "deckId": "lipstick",
        "lang": "eng",
        "slides": [
            {
                "slideId": "slide-1",
                "slideNumber": 1,
                "pageNumber": 1,
                "assetPath": "assets/fake.png",
                "blocks": [],
                "titleText": "Cached title",
                "bulletTexts": [],
                "figureRegions": [],
            }
        ],
    }
    fake_ocr_payload = {
        "deck_id": "lipstick",
        "lang": "eng",
        "slides": [
            {
                "slide_id": "slide-1",
                "slide_number": 1,
                "page_number": 1,
                "ocr_text": "Cached title block",
                "blocks": [],
                "figure_regions": [],
            }
        ],
    }
    fake_analysis = _fake_cached_analysis_payload()

    def _fake_render_pdf_deck(
        deck_id: str,
        deck_path: Path,
        pdf_bytes: bytes,
        storage,
        *,
        prompt_style: str,
        owner_email: str | None,
        shared_with: list[str],
    ) -> None:
        deck_path.mkdir(parents=True, exist_ok=True)
        (deck_path / "source.pdf").write_bytes(pdf_bytes)
        storage.save_deck(
            Deck(
                deck_id=deck_id,
                prompt_style=prompt_style,
                owner_email=owner_email,
                shared_with=shared_with,
                slides=[
                    Slide(
                        id="slide-1",
                        title_html="<h1>Cached title</h1>",
                        body_html="<p>Cached body</p>",
                    )
                ],
            )
        )

    monkeypatch.setattr("modules.slides.api._render_pdf_deck", _fake_render_pdf_deck)
    monkeypatch.setattr(
        "modules.slides.api._normalize_layout_payload",
        lambda payload, *, deck_id, lang: payload,
    )
    monkeypatch.setattr(
        "modules.slides.api._build_slide_analysis_payload",
        lambda layout_payload, ocr_payload, *, deck_id, lang: fake_analysis,
    )
    monkeypatch.setattr(
        "src.slides.layout_service.build_deck_layout_payload",
        lambda deck, deck_path, *, lang, **_kwargs: fake_layout_payload,
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_ocr_payload",
        lambda deck, deck_path, *, lang, include_bboxes, layout_payload, pdf_path, **_kwargs: fake_ocr_payload,
    )

    first_payload = validator.build_pdf_reading_payload_for_validation(pdf_path)

    def _unexpected_call(*args, **kwargs):
        raise AssertionError("reader cache should have been reused")

    monkeypatch.setattr("modules.slides.api._render_pdf_deck", _unexpected_call)
    monkeypatch.setattr(
        "src.slides.layout_service.build_deck_layout_payload",
        _unexpected_call,
    )
    monkeypatch.setattr(
        "src.slides.ocr_service.build_deck_ocr_payload",
        _unexpected_call,
    )
    monkeypatch.setattr(
        "modules.slides.api._build_slide_analysis_payload",
        _unexpected_call,
    )

    second_payload = validator.build_pdf_reading_payload_for_validation(pdf_path)

    assert second_payload["deck_id"] == first_payload["deck_id"]
    assert second_payload["lang"] == first_payload["lang"]
    assert second_payload["slides"] == first_payload["slides"]
    assert second_payload["reading_completeness"]["status"] == "read_ok"
