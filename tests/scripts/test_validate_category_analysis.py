from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from scripts import validate_category_analysis as validator


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if rows:
        pl.DataFrame(rows).write_csv(path)
        return
    pl.DataFrame().write_csv(path)


def _make_package_dir(tmp_path: Path) -> Path:
    package_dir = tmp_path / "pack"
    package_dir.mkdir()
    _write_csv(
        package_dir / "top_seller_pairs.csv",
        [
            {
                "bundle_label": "shine + cream",
                "count_top_seller": 10,
                "count_other": 15,
                "pct_top_seller": 10 / 18,
                "pct_other": 15 / 68,
                "top_seller_brand_count": 8,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_triples.csv",
        [
            {
                "bundle_label": "crueltyFree + colorDepositing + cream",
                "count_top_seller": 7,
                "count_other": 10,
                "pct_top_seller": 7 / 18,
                "pct_other": 10 / 68,
                "top_seller_brand_count": 6,
            },
            {
                "bundle_label": "crueltyFree + greyCoverage + cream",
                "count_top_seller": 7,
                "count_other": 12,
                "pct_top_seller": 7 / 18,
                "pct_other": 12 / 68,
                "top_seller_brand_count": 6,
            }
        ],
    )
    _write_csv(
        package_dir / "innovation_pairs.csv",
        [
            {
                "bundle_label": "natural + vegan",
                "count_recent": 5,
                "count_rest": 6,
                "pct_recent": 5 / 18,
                "pct_rest": 6 / 68,
                "recent_brand_count": 4,
            },
            {
                "bundle_label": "natural + cream",
                "count_recent": 7,
                "count_rest": 12,
                "pct_recent": 7 / 18,
                "pct_rest": 12 / 68,
                "recent_brand_count": 5,
            }
        ],
    )
    _write_csv(
        package_dir / "innovation_triples.csv",
        [
            {
                "bundle_label": "natural + vegan + bonder",
                "count_recent": 4,
                "count_rest": 5,
                "pct_recent": 4 / 18,
                "pct_rest": 5 / 68,
                "recent_brand_count": 4,
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "product form",
                "attribute_value": "cream",
                "count_top_seller": 6,
                "count_other": 32,
                "top_seller_base": 13,
                "other_base": 55,
                "pct_top_seller": 6 / 13,
                "pct_other": 32 / 55,
            }
        ],
    )
    _write_csv(
        package_dir / "mapped_attribute_comparison.csv",
        [
            {
                "attribute_name": "ingredient preference",
                "attribute_value": "vegan",
                "count_recent": 10,
                "count_rest": 28,
                "recent_base": 10,
                "rest_base": 50,
                "pct_recent": 1.0,
                "pct_rest": 0.56,
            }
        ],
    )
    _write_csv(
        package_dir / "filter_comparison.csv",
        [
            {
                "filter_family": "ingredient preference",
                "filter_value": "vegan",
                "count_recent": 10,
                "count_rest": 28,
                "recent_family_base": 10,
                "rest_family_base": 50,
                "pct_recent": 1.0,
                "pct_rest": 0.56,
            },
            {
                "filter_family": "product benefit",
                "filter_value": "bonder",
                "count_recent": 4,
                "count_rest": 3,
                "recent_family_base": 10,
                "rest_family_base": 19,
                "pct_recent": 0.4,
                "pct_rest": 3 / 19,
            },
            {
                "filter_family": "product benefit",
                "filter_value": "PreColor",
                "count_recent": 4,
                "count_rest": 3,
                "recent_family_base": 10,
                "rest_family_base": 19,
                "pct_recent": 0.4,
                "pct_rest": 3 / 19,
            }
        ],
    )
    _write_csv(package_dir / "resolved_core_comparison.csv", [])
    _write_csv(
        package_dir / "top_seller_brand_comparison.csv",
        [
            {
                "brand": "Dior",
                "catalog_count": 2,
                "top_seller_count": 1,
                "other_count": 1,
                "catalog_share": 0.07,
                "top_seller_share_of_brand": 0.5,
                "top_seller_share_of_cohort": 0.10,
                "over_index_vs_catalog_share": 1.43,
            },
            {
                "brand": "Chanel",
                "catalog_count": 1,
                "top_seller_count": 1,
                "other_count": 0,
                "catalog_share": 0.05,
                "top_seller_share_of_brand": 1.0,
                "top_seller_share_of_cohort": 0.05,
                "over_index_vs_catalog_share": 1.0,
            },
            {
                "brand": "Kenra Professional",
                "catalog_count": 3,
                "top_seller_count": 1,
                "other_count": 2,
                "catalog_share": 0.05,
                "top_seller_share_of_brand": 0.33,
                "top_seller_share_of_cohort": 0.1195,
                "over_index_vs_catalog_share": 2.39,
            },
        ],
    )
    _write_csv(
        package_dir / "recent_products.csv",
        [
            {
                "product_name": "Hero Product",
                "brand": "Dior",
                "pareto_rank": 11,
                "pareto_bucket": "A",
            },
            {
                "product_name": "NEW! Majirel Permanent Color 2oz.",
                "brand": "Pravana",
                "pareto_rank": 1,
                "pareto_bucket": "A",
            }
        ],
    )
    _write_csv(
        package_dir / "top_seller_products.csv",
        [
            {
                "product_name": "Hero Product",
                "brand": "Dior",
                "pareto_rank": 11,
                "pareto_bucket": "A",
            },
            {
                "product_name": "NEW! Majirel Permanent Color 2oz.",
                "brand": "Pravana",
                "pareto_rank": 1,
                "pareto_bucket": "A",
            }
        ],
    )
    return package_dir


def test_validate_analysis_markdown_passes_when_bundle_brand_and_product_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "\n".join(
            [
                "`shine + cream` appears in 55.6% of top sellers vs 22.1% of others across 8 brands.",
                "Dior is 10.0% of the top-seller cohort from 7.0% of catalog share (1.43x over-index).",
                "Hero Product (#11 Pareto A)",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "`shine + cream` appears in 55.6% of top sellers vs 22.1% of others across 8 brands.",
                    "claim_type": "bundle",
                    "entity_text": "shine + cream",
                },
                {
                    "claim_text": "Dior is 10.0% of the top-seller cohort from 7.0% of catalog share (1.43x over-index).",
                    "claim_type": "brand",
                    "entity_text": "Dior",
                },
                {
                    "claim_text": "Hero Product (#11 Pareto A)",
                    "claim_type": "product_rank",
                    "entity_text": "Hero Product",
                },
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["failure_count"] == 0
    assert payload["summary"]["checked_count"] >= 3


def test_validate_analysis_markdown_fails_when_number_matches_other_brand_not_target_brand(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Dior is 5.0% of the top-seller cohort from 5.0% of catalog share (1.0x over-index).",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Dior is 5.0% of the top-seller cohort from 5.0% of catalog share (1.0x over-index).",
                    "claim_type": "brand",
                    "entity_text": "Dior",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "fail"
    assert payload["summary"]["failure_count"] == 1
    failure = payload["failures"][0]
    assert failure["brand"] == "Dior"
    assert "brand percent mismatch" in failure["reasons"][0]


def test_validate_analysis_markdown_uses_bundle_entity_text_without_backticks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Cream and shine appears in 55.6% of top sellers vs 22.1% of others across 8 brands.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Cream and shine appears in 55.6% of top sellers vs 22.1% of others across 8 brands.",
                    "claim_type": "bundle",
                    "entity_text": "cream and shine",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["checked_count"] == 1
    assert payload["checked"][0]["entity_type"] == "bundle"


def test_validate_analysis_markdown_normalizes_prefixed_bundle_label(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "`product benefit=shine + product form=cream` appears in 55.6% of top sellers vs 22.1% of others across 8 brands.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "`product benefit=shine + product form=cream` appears in 55.6% of top sellers vs 22.1% of others across 8 brands.",
                    "claim_type": "bundle",
                    "entity_text": "product benefit=shine + product form=cream",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["warning_count"] == 0
    assert payload["checked"][0]["entity_type"] == "bundle"


def test_validate_analysis_markdown_warns_when_brand_claim_has_no_numeric_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Dior remains over-indexed in the top-seller cohort.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Dior remains over-indexed in the top-seller cohort.",
                    "claim_type": "brand",
                    "entity_text": "Dior",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["failure_count"] == 0
    assert payload["summary"]["warning_count"] == 1
    assert payload["warnings"][0]["brand"] == "Dior"
    assert payload["warnings"][0]["message"] == "brand claim missing numeric evidence to validate"


def test_validate_analysis_markdown_matches_short_brand_alias_to_package_brand(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Kenra also over-indexes at 2.39x.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Kenra also over-indexes at 2.39x.",
                    "claim_type": "brand",
                    "entity_text": "Kenra",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["warning_count"] == 0
    assert payload["checked"][0]["entity"] == "Kenra Professional"


def test_validate_analysis_markdown_reclassifies_plain_brand_mentions_as_non_deterministic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "L'ANZA Healing Color reviews mention true-to-tone color, 100% grey coverage, and shiny, healthy-feeling hair.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "L'ANZA Healing Color reviews mention true-to-tone color, 100% grey coverage, and shiny, healthy-feeling hair.",
                    "claim_type": "brand",
                    "entity_text": "L'ANZA",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["failure_count"] == 0
    assert payload["summary"]["warning_count"] == 0
    assert payload["summary"]["non_deterministic_claim_count"] == 1
    assert payload["non_deterministic_claims"][0]["entity_text"] == "L'ANZA"
    assert payload["non_deterministic_claims"][0]["reason"] == "plain_brand_mention"


def test_validate_analysis_markdown_adds_llm_narrative_review_for_non_deterministic_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Redken reviews are blunt: long wear and stubborn grey coverage.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Redken reviews are blunt: long wear and stubborn grey coverage.",
                    "claim_type": "non_deterministic",
                    "entity_text": "Redken",
                }
            ],
        },
    )
    monkeypatch.setattr(
        validator,
        "_review_non_deterministic_claims_with_llm",
        lambda **_: [
            {
                "claim_text": "Redken reviews are blunt: long wear and stubborn grey coverage.",
                "entity_text": "Redken",
                "verdict": "supported",
                "reason": "The review snippets directly mention long wear and grey coverage.",
                "evidence_ids": ["E1", "E2"],
                "evidence_snippets": [
                    {"id": "E1", "snippet": "[top_seller_review_validation.csv] ..."}
                ],
            }
        ],
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
        review_non_deterministic=True,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["narrative_review_count"] == 1
    assert payload["summary"]["narrative_verdict_counts"]["supported"] == 1
    assert payload["narrative_claim_reviews"][0]["verdict"] == "supported"


def test_validate_analysis_markdown_does_not_run_brand_validation_for_bundle_claims(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "`shine + cream` appears in 55.6% of top sellers vs 22.1% of others and skews toward Dior and Chanel.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "`shine + cream` appears in 55.6% of top sellers vs 22.1% of others and skews toward Dior and Chanel.",
                    "claim_type": "bundle",
                    "entity_text": "shine + cream",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["failure_count"] == 0
    assert payload["summary"]["warning_count"] == 0
    assert payload["summary"]["checked_count"] == 1
    assert payload["checked"][0]["entity_type"] == "bundle"


def test_validate_analysis_markdown_checks_recent_single_attribute_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Among products with ingredient-preference observations, vegan is on 100% of recent vs 56% of rest.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Among products with ingredient-preference observations, vegan is on 100% of recent vs 56% of rest.",
                    "claim_type": "bundle",
                    "entity_text": "vegan",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["failure_count"] == 0
    assert payload["summary"]["warning_count"] == 0
    assert payload["checked"][0]["entity"] == "vegan"


def test_validate_analysis_markdown_localizes_bundle_clause_before_checking(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        (
            "The strongest recent lifts are ingredient preference=vegan + product form=cream "
            "at 38.9% of recent vs 16.2% of rest across 5 brands, and "
            "haircolor tone=natural + product form=cream at 38.9% vs 17.6% across 5 brands."
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": (
                        "The strongest recent lifts are ingredient preference=vegan + product form=cream "
                        "at 38.9% of recent vs 16.2% of rest across 5 brands, and "
                        "haircolor tone=natural + product form=cream at 38.9% vs 17.6% across 5 brands."
                    ),
                    "claim_type": "bundle",
                    "entity_text": "natural + cream",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["failure_count"] == 0
    assert payload["checked"][0]["entity"] == "natural + cream"
    assert payload["checked"][0]["segment"] == "haircolor tone=natural + product form=cream at 38.9% vs 17.6% across 5 brands."


def test_validate_analysis_markdown_downgrades_ambiguous_multi_claim_bundle_failure_to_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        (
            "The only additions worth keeping are "
            "`ingredient preference=crueltyFree + product benefit=colorDepositing + product form=cream` "
            "at 38.9% of top sellers vs 14.7% of others and "
            "`crueltyFree + greyCoverage + cream` at 38.9% vs 17.6%."
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": (
                        "The only additions worth keeping are "
                        "`ingredient preference=crueltyFree + product benefit=colorDepositing + product form=cream` "
                        "at 38.9% of top sellers vs 14.7% of others and "
                        "`crueltyFree + greyCoverage + cream` at 38.9% vs 17.6%."
                    ),
                    "claim_type": "bundle",
                    "entity_text": "crueltyFree + greyCoverage + cream",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["failure_count"] == 0
    assert payload["summary"]["warning_count"] == 1
    assert (
        payload["warnings"][0]["message"]
        == "multi-claim bundle sentence could not be cleanly disambiguated"
    )


def test_validate_analysis_markdown_splits_shared_metric_bundle_labels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "bonder and PreColor each appear on 40% of recent vs 15.8% of rest.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "bonder and PreColor each appear on 40% of recent vs 15.8% of rest.",
                    "claim_type": "bundle",
                    "entity_text": "bonder + PreColor",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["warning_count"] == 0
    assert {item["entity"] for item in payload["checked"]} == {"bonder", "PreColor"}


def test_validate_analysis_markdown_reclassifies_synthetic_bundle_cluster_as_non_deterministic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "The broader care/performance cream cluster usually spans 7 brands.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "The broader care/performance cream cluster usually spans 7 brands.",
                    "claim_type": "bundle",
                    "entity_text": "care/performance + cream",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["warning_count"] == 0
    assert payload["summary"]["non_deterministic_claim_count"] == 1
    assert payload["non_deterministic_claims"][0]["entity_text"] == "care/performance + cream"
    assert payload["non_deterministic_claims"][0]["reason"] == "synthetic_bundle_cluster"


def test_validate_analysis_markdown_uses_product_entity_text_with_flexible_rank_format(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Hero Product sits in Pareto A at rank #11.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Hero Product sits in Pareto A at rank #11.",
                    "claim_type": "product_rank",
                    "entity_text": "Hero Product",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["checked_count"] == 1
    assert payload["checked"][0]["entity"] == "Hero Product"


def test_validate_analysis_markdown_matches_product_alias_with_reordered_tokens(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Majirel NEW! sits in Pareto A at rank #1.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Majirel NEW! sits in Pareto A at rank #1.",
                    "claim_type": "product_rank",
                    "entity_text": "Majirel NEW!",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["warning_count"] == 0
    assert payload["checked"][0]["entity"] == "NEW! Majirel Permanent Color 2oz."


def test_validate_analysis_markdown_strips_rank_annotation_from_product_entity_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "Majirel NEW! (#1 Pareto A)",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": "Majirel NEW! (#1 Pareto A)",
                    "claim_type": "product_rank",
                    "entity_text": "Majirel NEW! (#1 Pareto A)",
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["warning_count"] == 0
    assert payload["checked"][0]["entity"] == "NEW! Majirel Permanent Color 2oz."


def test_validate_analysis_markdown_splits_multi_product_rank_entity_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        (
            "That recurring four-brand product set is Majirel NEW! (#1 Pareto A), "
            "Pravana ChromaSilk (#7 A), Kevin.Murphy COLOR.ME (#18 A), "
            "and R+Co OMNIPRESENT (#33 B)."
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [
                {
                    "claim_text": (
                        "That recurring four-brand product set is Majirel NEW! (#1 Pareto A), "
                        "Pravana ChromaSilk (#7 A), Kevin.Murphy COLOR.ME (#18 A), "
                        "and R+Co OMNIPRESENT (#33 B)."
                    ),
                    "claim_type": "product_rank",
                    "entity_text": (
                        "Majirel NEW! (#1 Pareto A), Pravana ChromaSilk (#7 A), "
                        "Kevin.Murphy COLOR.ME (#18 A), and R+Co OMNIPRESENT (#33 B)"
                    ),
                }
            ],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
        validate_output_contract=False,
    )

    assert payload["status"] == "pass_with_warnings"
    assert payload["summary"]["failure_count"] == 0
    assert payload["summary"]["checked_count"] == 1
    assert payload["summary"]["warning_count"] == 3
    assert payload["checked"][0]["entity"] == "NEW! Majirel Permanent Color 2oz."


def test_validate_analysis_markdown_checks_required_output_contract(tmp_path: Path, monkeypatch) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "\n".join(
            [
                "## Winning now",
                "The clearest winning bundle is shine + cream.",
                "## Brand context",
                "Dior is present but not the whole story.",
                "## PDP/review validation of winners",
                "Reviews broadly support shine + cream.",
                "## Innovation layer",
                "Natural + vegan is the emerging bundle.",
                "## Innovation vs winners",
                "The emerging signal overlaps with current winners only partially.",
                "## What did not produce a clear signal",
                "Price architecture is noisy.",
                "## Standout products",
                "Hero Product is the clearest example.",
                "## Factual synthesis",
                "The category is led by shine + cream while natural + vegan is building.",
                "## Analytical recap block",
                "- Winning now: shine + cream",
                "- Emerging signal: natural + vegan",
                "- Brand effect level: medium",
                "- Confidence: high",
                "- Most relevant examples: Hero Product",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["output_contract_failure_count"] == 0
    assert payload["summary"]["output_contract_checked_count"] == 14


def test_validate_analysis_markdown_accepts_analytical_recap_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "\n".join(
            [
                "## Winning now",
                "The clearest winning bundle is shine + cream.",
                "## Brand context",
                "Dior is present but not the whole story.",
                "## PDP/review validation of winners",
                "Reviews broadly support shine + cream.",
                "## Innovation layer",
                "Natural + vegan is the emerging bundle.",
                "## Innovation vs winners",
                "The emerging signal overlaps with current winners only partially.",
                "## What did not produce a clear signal",
                "Price architecture is noisy.",
                "## Standout products",
                "Hero Product is the clearest example.",
                "## Factual synthesis",
                "The category is led by shine + cream while natural + vegan is building.",
                "## Analytical recap",
                "- Winning now: shine + cream",
                "- Emerging signal: natural + vegan",
                "- Brand effect level: medium",
                "- Confidence: high",
                "- Most relevant examples: Hero Product",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
    )

    assert payload["status"] == "pass"
    assert payload["summary"]["output_contract_failure_count"] == 0


def test_validate_analysis_markdown_fails_when_required_section_missing(tmp_path: Path, monkeypatch) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "\n".join(
            [
                "## Winning now",
                "The clearest winning bundle is shine + cream.",
                "## Brand context",
                "Dior is present but not the whole story.",
                "## PDP/review validation of winners",
                "Reviews broadly support shine + cream.",
                "## Innovation vs winners",
                "The emerging signal overlaps with current winners only partially.",
                "## What did not produce a clear signal",
                "Price architecture is noisy.",
                "## Standout products",
                "Hero Product is the clearest example.",
                "## Factual synthesis",
                "The category is led by shine + cream while natural + vegan is building.",
                "## Analytical recap block",
                "- Winning now: shine + cream",
                "- Emerging signal: natural + vegan",
                "- Brand effect level: medium",
                "- Confidence: high",
                "- Most relevant examples: Hero Product",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
    )

    assert payload["status"] == "fail"
    assert payload["summary"]["output_contract_failure_count"] == 1
    assert payload["output_contract_failures"][0]["entity"] == "Innovation layer"


def test_validate_analysis_markdown_fails_when_recap_level_is_invalid(tmp_path: Path, monkeypatch) -> None:
    package_dir = _make_package_dir(tmp_path)
    analysis_path = tmp_path / "analysis.md"
    analysis_path.write_text(
        "\n".join(
            [
                "## Winning now",
                "The clearest winning bundle is shine + cream.",
                "## Brand context",
                "Dior is present but not the whole story.",
                "## PDP/review validation of winners",
                "Reviews broadly support shine + cream.",
                "## Innovation layer",
                "Natural + vegan is the emerging bundle.",
                "## Innovation vs winners",
                "The emerging signal overlaps with current winners only partially.",
                "## What did not produce a clear signal",
                "Price architecture is noisy.",
                "## Standout products",
                "Hero Product is the clearest example.",
                "## Factual synthesis",
                "The category is led by shine + cream while natural + vegan is building.",
                "## Analytical recap block",
                "- Winning now: shine + cream",
                "- Emerging signal: natural + vegan",
                "- Brand effect level: concentrated",
                "- Confidence: high",
                "- Most relevant examples: Hero Product",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "extract_claims_for_validation",
        lambda **_: {
            "mode": "llm",
            "claims": [],
        },
    )

    payload = validator.validate_analysis_markdown(
        package_dir=package_dir,
        analysis_markdown=analysis_path,
    )

    assert payload["status"] == "fail"
    assert payload["summary"]["output_contract_failure_count"] == 1
    assert payload["output_contract_failures"][0]["entity"] == "Brand effect level"


def test_write_validation_artifacts_creates_json_and_markdown(tmp_path: Path) -> None:
    payload = {
        "status": "pass_with_warnings",
        "analysis_markdown": str((tmp_path / "analysis.md").resolve()),
        "summary": {
            "checked_count": 1,
            "warning_count": 1,
            "failure_count": 0,
            "non_deterministic_claim_count": 1,
            "narrative_review_count": 1,
            "narrative_verdict_counts": {"supported": 1},
            "output_contract_checked_count": 8,
            "output_contract_warning_count": 0,
            "output_contract_failure_count": 1,
        },
        "checked": [
            {
                "entity_type": "bundle",
                "entity": "shine + cream",
                "file": "top_seller_pairs.csv",
            }
        ],
        "warnings": [
            {
                "label": "product benefit=shine + product form=cream",
                "segment": "Joico line",
                "message": "no matching package row found for label",
            }
        ],
        "output_contract_failures": [
            {"entity": "Analytical recap block", "message": "missing analytical recap block"}
        ],
        "output_contract_warnings": [],
        "failures": [],
        "non_deterministic_claims": [{"claim_text": "Joico reviews imply softer fade."}],
        "narrative_claim_reviews": [
            {
                "claim_text": "Joico reviews imply softer fade.",
                "verdict": "supported",
                "reason": "Review snippets mention low fade.",
                "evidence_ids": ["E1"],
            }
        ],
        "unvalidated_note": "Narrative validation is out of scope.",
    }
    output_prefix = tmp_path / "analysis"

    json_path, md_path = validator.write_validation_artifacts(
        payload=payload,
        output_prefix=output_prefix,
    )

    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "pass_with_warnings"
    markdown = md_path.read_text(encoding="utf-8")
    assert "Status: **pass_with_warnings**" in markdown
    assert "Fix `1` blocking issue(s) first." in markdown
    assert "`1` item(s): no matching package row found for label" in markdown
    assert "`product benefit=shine + product form=cream`" in markdown
    assert "## Narrative LLM Review" in markdown
    assert "## Narrative Claim Outcomes" in markdown
    assert "`supported`: `1`" in markdown
    assert "`supported`: Joico reviews imply softer fade." in markdown
    assert "Note: Review snippets mention low fade." in markdown
