from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from modules.add_attributes import pdp_attribute_export as exporter
from modules.add_attributes.attribute_classification import NOT_IN_TAXONOMY_VALUE
from modules.pdp.store import AttributeValueRecord


def test_normalize_stage_value_canonicalizes_placeholders() -> None:
    assert exporter._normalize_stage_value("n/a (not stated)") == "N/A"
    assert exporter._normalize_stage_value("NA") == "N/A"
    assert exporter._normalize_stage_value("unknown") == "N/A"


@pytest.mark.parametrize(
    ("values_by_source", "expected"),
    [
        pytest.param(
            {"codex": "Dewy", "vision": "Matte"},
            ("Dewy", "codex"),
            id="codex-effective",
        ),
        pytest.param(
            {"retailer_filter": "Matte", "codex": "Dewy"},
            ("Matte", "retailer_filter"),
            id="retailer-filter-authoritative",
        ),
        pytest.param(
            {"deterministic_explicit": "Natural", "codex": "Dewy"},
            ("Natural", "deterministic_explicit"),
            id="explicit-authoritative",
        ),
    ],
)
def test_choose_canonical_attribute_value_retains_winning_source(
    values_by_source: dict[str, str], expected: tuple[str, str]
) -> None:
    assert (
        exporter._choose_canonical_attribute_value_and_source(values_by_source)
        == expected
    )


def test_clean_attribute_columns_flattens_list_values_for_export() -> None:
    df = pl.DataFrame(
        {
            "parent_product_id": ["p1", "p2"],
            "benefits": [["hydrating", "vegan", "hydrating"], ["N/A"]],
        }
    )

    cleaned = exporter._clean_attribute_columns(df, ["benefits"])

    assert cleaned.schema["benefits"] == pl.Utf8
    assert cleaned.get_column("benefits").to_list() == ["hydrating | vegan", None]


def test_join_classification_overrides_replaces_stale_attribute_columns() -> None:
    base_df = pl.DataFrame(
        {
            "product_name": ["Tinted Moisturizer"],
            "category_key": ["tinted_moisturizer"],
            "spf": ["4"],
            "finish": ["natural"],
        }
    )
    classification_df = pl.DataFrame(
        {
            "product_name": ["Tinted Moisturizer"],
            "category_key": ["tinted_moisturizer"],
            "spf": ["50"],
        }
    )

    joined = exporter._join_classification_overrides(
        base_df,
        classification_df,
        key_columns=["product_name", "category_key"],
    )

    row = joined.row(0, named=True)
    assert row["spf"] == "50"
    assert row["finish"] == "natural"


def test_apply_ulta_face_authority_to_export_frame_prefers_ulta_values() -> None:
    frame = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta", "ulta"],
            "parent_product_id": ["parent-1", "lip-1", "brow-1"],
            "category_key": ["tinted_moisturizer", "lip_gloss", "eyebrow"],
            "form": ["skin tint", "oil", "gel"],
            "coverage": ["light", "sheer", None],
            "color family": ["gold", "rose", None],
            "shade family": [None, None, "auburn"],
            "spf": ["4", "", None],
            "free from": [None, "paraben-free", None],
        }
    )
    authority = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta", "ulta"],
            "parent_product_id": ["parent-1", "lip-1", "brow-1"],
            "category_key": ["tinted_moisturizer", "lip_gloss", "eyebrow"],
            "ulta_filter_form": ["liquid", None, "pencil"],
            "ulta_filter_spf": ["50+", None, None],
            "ulta_filter_color": ["neutral", None, None],
            "ulta_filter_preference": [None, "vegan", None],
            "ulta_filter_color_eyes": [None, None, "brown"],
        }
    )

    out = exporter._apply_ulta_face_authority_to_export_frame(
        frame,
        authority_df=authority,
    )

    face_row = out.filter(pl.col("parent_product_id") == "parent-1").row(0, named=True)
    assert face_row["form"] == "liquid"
    assert face_row["our_form"] == "skin tint"
    assert face_row["ulta_form"] == "liquid"
    assert face_row["form_authority_source"] == "ulta"
    assert face_row["spf"] == "50+"
    assert face_row["our_spf"] == "4"
    assert face_row["spf_authority_source"] == "ulta"
    assert face_row["color family"] == "neutral"
    assert face_row["our_color_family"] == "gold"
    assert face_row["color_family_authority_source"] == "ulta"
    assert face_row["coverage"] == "light"
    assert face_row["coverage_authority_source"] == "ours"

    brow_row = out.filter(pl.col("parent_product_id") == "brow-1").row(0, named=True)
    assert brow_row["form"] == "pencil"
    assert brow_row["our_form"] == "gel"
    assert brow_row["shade family"] == "brown"
    assert brow_row["our_shade_family"] == "auburn"
    assert brow_row["shade_family_authority_source"] == "ulta"

    lip_row = out.filter(pl.col("parent_product_id") == "lip-1").row(0, named=True)
    assert lip_row["form"] == "oil"
    assert lip_row["form_authority_source"] == "ours"
    assert lip_row["ulta_filter_preference"] == "vegan"


def test_attribute_enabled_for_category_suppresses_permanent_tone_and_level() -> None:
    assert (
        exporter._attribute_enabled_for_category(
            "permanent",
            "category",
            row_scope="parent",
        )
        is False
    )
    assert (
        exporter._attribute_enabled_for_category(
            "permanent",
            "haircolor_tone",
            row_scope="variant",
        )
        is False
    )
    assert (
        exporter._attribute_enabled_for_category(
            "permanent",
            "haircolor_level",
            row_scope="parent",
        )
        is False
    )
    assert (
        exporter._attribute_enabled_for_category(
            "permanent",
            "benefit",
            row_scope="variant",
        )
        is True
    )


def test_build_attribute_map_excludes_permanent_tone_and_level() -> None:
    taxonomy = {
        "categories": [
            {
                "id": "permanent",
                "label": "Permanent",
                "attributes": [
                    {"id": "category", "label": "Product Type"},
                    {"id": "benefit", "label": "Benefit"},
                    {"id": "haircolor_tone", "label": "Tone"},
                    {"id": "haircolor_level", "label": "Level"},
                ],
            }
        ]
    }

    attr_map = exporter._build_attribute_map(
        taxonomy,
        ["permanent"],
        row_scope="variant",
    )

    assert attr_map == {"permanent": ["benefit"]}


def test_build_attribute_map_respects_variant_scope() -> None:
    taxonomy = {
        "categories": [
            {
                "id": "lipstick",
                "label": "Lipstick",
                "attributes": [
                    {"id": "finish", "label": "Finish", "scope": "variant"},
                    {"id": "benefit", "label": "Benefit", "scope": "product"},
                    {"id": "legacy_attr", "label": "Legacy Attr"},
                ],
            }
        ]
    }

    parent_attr_map = exporter._build_attribute_map(
        taxonomy,
        ["lipstick"],
        row_scope="parent",
    )
    variant_attr_map = exporter._build_attribute_map(
        taxonomy,
        ["lipstick"],
        row_scope="variant",
    )

    assert parent_attr_map == {"lipstick": ["benefit", "legacy_attr"]}
    assert variant_attr_map == {"lipstick": ["finish", "legacy_attr"]}


def test_build_filter_alignment_report_uses_ulta_bridge_labels() -> None:
    category_branch = {
        "id": "foundation",
        "label": "foundation",
        "attributes": [
            {
                "id": "form",
                "label": "form",
                "nodes": [
                    {"id": "liquid", "label": "liquid"},
                    {"id": "unknown", "label": "N/A (not stated)"},
                    {"id": "other", "label": "not in taxonomy"},
                ],
            },
            {
                "id": "skin_type",
                "label": "suitable skin type",
                "nodes": [
                    {"id": "sensitive", "label": "sensitive"},
                    {"id": "unknown", "label": "N/A (not stated)"},
                    {"id": "other", "label": "not in taxonomy"},
                ],
            },
            {
                "id": "spf",
                "label": "SPF",
                "nodes": [
                    {"id": "spf_50_plus", "label": "50+"},
                    {"id": "unknown", "label": "N/A (not stated)"},
                    {"id": "other", "label": "not in taxonomy"},
                ],
            },
        ],
    }
    observed_filters = {
        "form": {"label": "form", "values": {"liquid": "Liquid"}},
        "skin type": {"label": "skin type", "values": {"sensitive": "Sensitive"}},
        "spf": {"label": "spf", "values": {"50+": "50+"}},
    }

    report = exporter._build_filter_alignment_report(
        category_branch,
        observed_filters,
        retailer="ulta",
        category_key="foundation",
    )

    assert report["missing_filter_dimensions"] == []
    assert sorted(report["bridged_taxonomy_dimensions"]) == [
        "SPF",
        "form",
        "suitable skin type",
    ]
    assert report["value_alignment"]["form"]["missing_filter_values"] == []


def test_normalize_stage_value_preserves_meaningful_and_taxonomy_values() -> None:
    assert exporter._normalize_stage_value("Comb") == "Comb"
    expected_taxonomy = NOT_IN_TAXONOMY_VALUE
    assert (
        exporter._normalize_stage_value(expected_taxonomy.upper()) == expected_taxonomy
    )


def test_build_parent_source_segment_rows_maps_expected_channels() -> None:
    extras = {
        "summary": "Velvet matte finish",
        "details": {
            "description_markdown": "Comfortable matte lipstick.",
            "features": ["Long-wearing", "Smooth glide"],
            "ingredients": "Dimethicone, Silica",
            "usage": "Swipe on lips.",
            "restrictions": "External use only.",
        },
        "highlights": [
            {"label": "Finish", "description": "Soft matte"},
            {"label": "Texture", "description": "Creamy"},
        ],
        "summary_cards": [
            {"title": "Benefits", "items": ["Blurs lines", {"text": "Hydrating feel"}]}
        ],
        "reviews": [{"headline": "Love it", "comment": "Feels weightless"}],
        "reviews_positive": {
            "headline": "Best part",
            "comment": "Soft-focus look",
        },
        "reviews_negative": {
            "headline": "Drawback",
            "comment": "Can transfer",
        },
    }

    rows = exporter._build_parent_source_segment_rows(
        retailer="Amazon",
        parent_product_id="B0TESTSKU",
        category_key="lipstick",
        title_raw="Sample Lipstick Matte Finish",
        extras=extras,
    )
    frame = exporter._rows_to_pdp_source_segments_dataframe(rows)

    title_row = frame.filter(pl.col("source_path") == "title_raw").row(0, named=True)
    assert title_row["source_channel"] == "title"
    assert title_row["segment_text"] == "Sample Lipstick Matte Finish"
    assert title_row["normalized_text"] == "sample lipstick matte finish"

    assert (
        frame.filter(pl.col("source_path") == "details.features[0]")
        .get_column("source_channel")
        .item()
        == "features"
    )
    highlight_row = frame.filter(pl.col("source_path") == "highlights[0]").row(
        0, named=True
    )
    assert highlight_row["segment_text"] == "Finish: Soft matte"
    assert highlight_row["label"] == "Finish"
    summary_card_row = frame.filter(
        pl.col("source_path") == "summary_cards[0].items[0]"
    ).row(0, named=True)
    assert summary_card_row["segment_text"] == "Blurs lines"
    assert summary_card_row["label"] == "Benefits"
    review_row = frame.filter(pl.col("source_path") == "reviews[0].comment").row(
        0, named=True
    )
    assert review_row["source_channel"] == "reviews"
    assert review_row["subtype"] == "raw_comment"
    assert (
        frame.filter(pl.col("source_path") == "reviews_positive.comment")
        .get_column("subtype")
        .item()
        == "positive_comment"
    )


def test_build_variant_source_segment_rows_uses_variant_name_and_description() -> None:
    rows = exporter._build_variant_source_segment_rows(
        retailer="Amazon",
        parent_product_id="B0TESTSKU",
        variant_id="B0TESTSKU-001",
        category_key="lipstick",
        shade_name_raw="Crimson",
        size_text_raw="0.12 oz",
        extras={
            "name": "Crimson",
            "details": {"features": ["Warm undertone"]},
        },
    )
    frame = exporter._rows_to_pdp_source_segments_dataframe(rows)

    assert (
        frame.filter(pl.col("source_path") == "shade_name_raw")
        .get_column("source_channel")
        .item()
        == "variant_name"
    )
    assert frame.filter(pl.col("source_path") == "size_text_raw").is_empty()
    assert (
        frame.filter(pl.col("source_path") == "name")
        .get_column("source_channel")
        .item()
        == "variant_description"
    )
    assert (
        frame.filter(pl.col("source_path") == "details.features[0]")
        .get_column("segment_text")
        .item()
        == "Warm undertone"
    )


def test_collect_all_text_segments_skips_review_fields() -> None:
    segments = exporter._collect_all_text_segments(
        {
            "name": "Crimson",
            "details": {"features": ["Warm undertone"]},
            "reviews": [{"headline": "Love it", "comment": "Not sticky"}],
            "reviews_positive": {"comment": "Glossy"},
        }
    )

    paths = {path for path, _text in segments}
    assert "name" in paths
    assert "details.features[0]" in paths
    assert all(not path.startswith("reviews") for path in paths)


def test_flatten_description_aggregates_all_non_review_text() -> None:
    extras = {
        "summary": "High-impact lipstick.",
        "short_description": "Short desc here.",
        "long_description": "Longer marketing paragraph.",
        "details": {"usage": "Apply directly.", "ingredients": "Vitamin E"},
        "highlights": [
            {"label": "Benefit", "description": "Feels great"},
            "Vegan friendly",
        ],
        "misc": [
            "Bonus note",
            {"nested": "Extra detail"},
        ],
        "reviews_positive": {"comment": "Loved it"},
        "reviews_negative": {"comment": "Too bold"},
    }

    description = exporter._flatten_description(extras)

    assert "High-impact lipstick." in description
    assert "Short desc here." in description
    assert "Longer marketing paragraph." in description
    assert "Apply directly." in description
    assert "Vitamin E" in description
    assert "Benefit" in description
    assert "Feels great" in description
    assert "Vegan friendly" in description
    assert "Bonus note" in description


def test_classify_stage_value_handles_not_stated_as_placeholder() -> None:
    assert exporter._classify_stage_value("n/a (not stated)") == "placeholder"


def test_apply_llm_choice_keeps_meaningful_deterministic_value() -> None:
    row = {"effect": "volumizing"}
    exporter._apply_llm_choice(row, "effect", "n/a (not stated)")
    assert row["effect"] == "volumizing"


def test_apply_llm_choice_normalizes_not_stated_placeholder() -> None:
    row = {"effect": "n/a (not stated)"}
    exporter._apply_llm_choice(row, "effect", None)
    assert row["effect"] == "N/A"


def test_collect_attribute_records_includes_llm_note_and_oov() -> None:
    df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "category_key": "lipstick",
                "finish": "matte",
            }
        ]
    )
    metadata = {
        ("Amazon", "parent", "P1", "", "lipstick", "finish"): (
            exporter._AttributeRecordMeta(
                oov_candidate="soft matte",
                note="Marketing text says soft matte.",
            )
        )
    }

    records = exporter._collect_attribute_records(
        df,
        row_type="parent",
        attr_labels={"finish": "Finish"},
        source="llm",
        timestamp="2026-02-09T00:00:00Z",
        allowed_columns={"finish"},
        attribute_metadata=metadata,
    )

    assert len(records) == 1
    assert records[0].oov_candidate == "soft matte"
    assert records[0].note == "Marketing text says soft matte."


def test_parse_pdp_response_handles_spaced_attribute_names() -> None:
    request = exporter._ParentLLMRequest(
        row_index=0,
        parent_product_id="PARENT-1",
        display_name="Sample Product",
        category_label="Lipstick",
        category_path="Beauty > Lipstick",
        deterministic_text="",
        pdp_text="",
        missing_attrs=["target_concerns"],
        allowed_values={"target_concerns": ["Hydration", "Dryness"]},
        nodes_by_label={"target_concerns": []},
        attr_column_map={"target_concerns": "target_concerns"},
        variants=[
            exporter._VariantLLMRequest(
                row_index=0,
                variant_id="SKU-1",
                variant_key="SKU-1",
                display_name="Variant 1",
                context_text="",
                missing_attrs=["primary_finish"],
                allowed_values={"primary_finish": ["Matte", "Satin"]},
                nodes_by_label={"primary_finish": []},
                attr_column_map={"primary_finish": "primary_finish"},
            )
        ],
    )
    response = {
        "parent": {
            "Target Concerns": {"value": "Hydration"},
            "Primary-Finish": {"value": "Matte"},
        },
        "variants": {
            "SKU-1": {
                "Primary Finish": {"value": "Matte"},
            }
        },
    }

    parsed = exporter._parse_pdp_response(response, request)

    assert parsed["parent"]["target_concerns"].value == "Hydration"
    assert parsed["variants"]["SKU-1"]["primary_finish"].value == "Matte"


def test_run_pdp_llm_batch_writes_dump(monkeypatch, tmp_path: Path) -> None:
    def fake_run_step_json(llm_wrapper, step, system_prompt, prompts, extra_body=None):
        assert step == "pdpClassificationQuery"
        assert len(list(prompts)) == 1
        assert extra_body == {"text": {"format": {"type": "json_schema"}}}
        return [{"parent": {"finish": {"value": "matte"}}, "variants": {}}]

    monkeypatch.setattr(
        "modules.llm.batch_runner.run_step_json",
        fake_run_step_json,
    )

    request = exporter._ParentLLMRequest(
        row_index=0,
        parent_product_id="PARENT-1",
        display_name="Sample Product",
        category_label="Lipstick",
        category_path="Beauty > Lipstick",
        deterministic_text="",
        pdp_text="",
        missing_attrs=["finish"],
        allowed_values={},
        nodes_by_label={},
        attr_column_map={"finish": "finish"},
        variants=[],
    )

    dump_path = tmp_path / "llm_dump.jsonl"
    results = exporter._run_pdp_llm_batch(
        object(),
        [request],
        "pdpClassificationQuery",
        extra_body={"text": {"format": {"type": "json_schema"}}},
        llm_dump_path=dump_path,
    )

    assert len(results) == 1
    assert results[0]["parent"]["finish"].value == "matte"
    assert results[0]["variants"] == {}
    content = dump_path.read_text(encoding="utf-8").splitlines()
    assert len(content) == 1
    record = json.loads(content[0])
    assert record["parent_product_id"] == "PARENT-1"
    assert record["response"]["parent"]["finish"]["value"] == "matte"


def test_fetch_parent_hero_url_extracts_kiko_primary(monkeypatch):
    payload = {
        "props": {
            "pageProps": {
                "root": {
                    "product_media": {
                        "primary_image": {
                            "url": "https://assets.example.com/blob/primary.webp"
                        }
                    }
                }
            }
        }
    }
    html = (
        '<html><head><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></head><body>"
        + '<img src="https://cdn.example.com/placeholder.jpg" />'
        + "</body></html>"
    )

    class DummyResponse:
        def __init__(self, body: str) -> None:
            self.text = body

        def raise_for_status(self) -> None:  # pragma: no cover - simple stub
            return None

    def fake_get(url, headers=None, timeout=None):  # noqa: D401 - test stub
        return DummyResponse(html)

    exporter._PARENT_HERO_CACHE.clear()
    monkeypatch.setattr(exporter.requests, "get", fake_get)

    result = exporter._fetch_parent_hero_url(
        "https://www.kikocosmetics.com/en-us/p/extra-volume-wash-off-mascara-18940/"
    )

    assert result == "https://assets.example.com/blob/primary.webp"


def test_llm_fill_pdp_attributes_batches_parent_and_variants(monkeypatch) -> None:
    taxonomy = {
        "categories": [
            {
                "id": "lipstick",
                "label": "Lipstick",
                "attributes": [
                    {"id": "finish", "label": "Finish", "scope": "parent"},
                    {
                        "id": "variant_finish",
                        "label": "Variant Finish",
                        "scope": "variant",
                    },
                ],
            }
        ]
    }
    parent_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "B0TESTSKU",
                "pdp_url": "https://example.com/pdp",
                "product_name": "Sample Lipstick",
                "brand": "Sample Brand",
                "category_key": "lipstick",
                "category_id": "lipstick",
                "category_label": "Lipstick",
                "raw_category_path": ["Beauty", "Lips", "Lipstick"],
                "description": "A matte lipstick with nourishing oils.",
                "finish": None,
            }
        ]
    )
    variant_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "variant_id": "B0TESTSKU-001",
                "variant_key": "B0TESTSKU:B0TESTSKU-001",
                "parent_product_id": "B0TESTSKU",
                "product_name": "Sample Lipstick",
                "brand": "Sample Brand",
                "category_key": "lipstick",
                "category_id": "lipstick",
                "category_label": "Lipstick",
                "description": "A matte lipstick.",
                "variant_description": "Shade description text.",
                "shade_name_raw": "Crimson",
                "size_text_raw": "0.12 oz",
                "variant_finish": None,
            }
        ]
    )

    def fake_get_naming_params() -> dict[str, str]:
        return {
            "pdpClassificationQuery": "pdpClassificationQuery",
            "classifyPdpAttributesQuery": "classifyPdpAttributesQuery",
            "attributeClassificationQuery": "attributeClassificationQuery",
        }

    captured: dict[str, list] = {}

    def fake_batch(llm_wrapper, requests, step, **kwargs):  # type: ignore[override]
        assert step == "pdpClassificationQuery"
        assert len(requests) == 1
        req = requests[0]
        captured["requests"] = requests
        assert req.missing_attrs == ["finish"]
        assert req.category_label == "Lipstick"
        assert req.category_path == "Beauty > Lips > Lipstick"
        assert req.variants and req.variants[0].missing_attrs == ["variant_finish"]
        assert "Shade description text" in req.variants[0].context_text
        return [
            {
                "parent": {
                    "finish": {
                        "value": "matte",
                        "oov_candidate": None,
                        "note": "Parent note",
                    }
                },
                "variants": {
                    "B0TESTSKU-001": {
                        "variant_finish": {
                            "value": "glossy",
                            "oov_candidate": "variant gloss candidate",
                            "note": "Variant note",
                        }
                    }
                },
            }
        ]

    monkeypatch.setattr(exporter, "get_naming_params", fake_get_naming_params)
    monkeypatch.setattr(exporter, "_run_pdp_llm_batch", fake_batch)

    parent_updated, variant_updated, llm_touched, llm_attribute_meta = (
        exporter._llm_fill_pdp_attributes(object(), parent_df, variant_df, taxonomy)
    )
    assert captured["requests"][0].pdp_text.startswith("A matte lipstick")

    parent_row = parent_updated.row(0, named=True)
    assert parent_row["finish"] == "matte"
    assert llm_touched["parent"] == {"finish"}

    variant_row = variant_updated.row(0, named=True)
    variant_column = (
        "variant finish"
        if "variant finish" in variant_updated.columns
        else "variant_finish"
    )
    assert variant_row[variant_column] == "glossy"
    assert llm_touched["variant"] == {variant_column}
    assert (
        llm_attribute_meta[
            ("Amazon", "parent", "B0TESTSKU", "", "lipstick", "finish")
        ].note
        == "Parent note"
    )
    assert (
        llm_attribute_meta[
            (
                "Amazon",
                "variant",
                "B0TESTSKU",
                "B0TESTSKU-001",
                "lipstick",
                variant_column,
            )
        ].oov_candidate
        == "variant gloss candidate"
    )


def test_llm_fill_requests_include_taxonomy_attributes_even_when_present(
    monkeypatch,
) -> None:
    taxonomy = {
        "categories": [
            {
                "id": "lipstick",
                "label": "Lipstick",
                "attributes": [
                    {"id": "finish", "label": "Finish", "scope": "parent"},
                ],
            }
        ]
    }
    parent_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "B0TESTSKU",
                "pdp_url": "https://example.com/pdp",
                "product_name": "Sample Lipstick",
                "brand": "Sample Brand",
                "category_key": "lipstick",
                "category_id": "lipstick",
                "category_label": "Lipstick",
                "raw_category_path": ["Beauty", "Lips", "Lipstick"],
                "description": "A matte lipstick with nourishing oils.",
                "finish": "n/a (not stated)",
            }
        ]
    )
    variant_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "variant_id": "B0TESTSKU-001",
                "variant_key": "B0TESTSKU:B0TESTSKU-001",
                "parent_product_id": "B0TESTSKU",
                "product_name": "Sample Lipstick",
                "brand": "Sample Brand",
                "category_key": "lipstick",
                "category_id": "lipstick",
                "category_label": "Lipstick",
                "description": "A matte lipstick.",
                "variant_description": "Shade description text.",
                "shade_name_raw": None,
                "size_text_raw": None,
            }
        ]
    )

    def fake_get_naming_params() -> dict[str, str]:
        return {
            "pdpClassificationQuery": "pdpClassificationQuery",
            "classifyPdpAttributesQuery": "classifyPdpAttributesQuery",
            "attributeClassificationQuery": "attributeClassificationQuery",
        }

    captured: dict[str, list] = {}

    def fake_batch(llm_wrapper, requests, step, **kwargs):  # type: ignore[override]
        assert step == "pdpClassificationQuery"
        assert len(requests) == 1
        req = requests[0]
        captured["requests"] = requests
        assert req.missing_attrs == ["finish"]
        return [{"parent": {"finish": "matte"}, "variants": {}}]

    monkeypatch.setattr(exporter, "get_naming_params", fake_get_naming_params)
    monkeypatch.setattr(exporter, "_run_pdp_llm_batch", fake_batch)

    parent_updated, variant_updated, llm_touched, _ = exporter._llm_fill_pdp_attributes(
        object(), parent_df, variant_df, taxonomy
    )
    assert captured["requests"][0].missing_attrs == ["finish"]

    parent_row = parent_updated.row(0, named=True)
    assert parent_row["finish"] == "matte"
    assert llm_touched["parent"] == {"finish"}
    assert not llm_touched["variant"]


def test_llm_fill_skips_request_when_nothing_missing(monkeypatch) -> None:
    taxonomy = {
        "categories": [
            {
                "id": "lipstick",
                "label": "Lipstick",
                "attributes": [
                    {"id": "finish", "label": "Finish", "scope": "parent"},
                    {
                        "id": "variant_finish",
                        "label": "Variant Finish",
                        "scope": "variant",
                    },
                ],
            }
        ]
    }
    parent_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "B0TESTSKU",
                "pdp_url": "https://example.com/pdp",
                "product_name": "Sample Lipstick",
                "brand": "Sample Brand",
                "category_key": "lipstick",
                "category_id": "lipstick",
                "category_label": "Lipstick",
                "raw_category_path": ["Beauty", "Lips", "Lipstick"],
                "description": "A matte lipstick with nourishing oils.",
                "finish": "matte",
            }
        ]
    )
    variant_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "variant_id": "B0TESTSKU-001",
                "variant_key": "B0TESTSKU:B0TESTSKU-001",
                "parent_product_id": "B0TESTSKU",
                "product_name": "Sample Lipstick",
                "brand": "Sample Brand",
                "category_key": "lipstick",
                "category_id": "lipstick",
                "category_label": "Lipstick",
                "description": "A matte lipstick.",
                "variant_description": "Shade description text.",
                "shade_name_raw": "Crimson",
                "size_text_raw": "0.12 oz",
                "variant_finish": "satin",
            }
        ]
    )

    called = {"value": False}

    def fail_batch(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        called["value"] = True
        raise AssertionError("LLM batch should not be called when nothing is missing.")

    monkeypatch.setattr(exporter, "_run_pdp_llm_batch", fail_batch)

    parent_updated, variant_updated, llm_touched, llm_attribute_meta = (
        exporter._llm_fill_pdp_attributes(object(), parent_df, variant_df, taxonomy)
    )

    assert called["value"] is False
    assert llm_touched == {"parent": set(), "variant": set()}
    assert llm_attribute_meta == {}
    assert parent_updated.row(0, named=True)["finish"] == "matte"
    assert variant_updated.row(0, named=True)["variant_finish"] == "satin"


def test_llm_fill_does_not_override_meaningful_with_placeholder(monkeypatch) -> None:
    taxonomy = {
        "categories": [
            {
                "id": "lipstick",
                "label": "Lipstick",
                "attributes": [
                    {"id": "finish", "label": "Finish", "scope": "parent"},
                ],
            }
        ]
    }
    parent_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "B0TESTSKU",
                "pdp_url": "https://example.com/pdp",
                "product_name": "Sample Lipstick",
                "brand": "Sample Brand",
                "category_key": "lipstick",
                "category_id": "lipstick",
                "category_label": "Lipstick",
                "raw_category_path": ["Beauty", "Lips", "Lipstick"],
                "description": "A matte lipstick with nourishing oils.",
                "finish": "satin",
            }
        ]
    )
    variant_df = pl.DataFrame()

    def fake_get_naming_params() -> dict[str, str]:
        return {
            "pdpClassificationQuery": "pdpClassificationQuery",
            "classifyPdpAttributesQuery": "classifyPdpAttributesQuery",
            "attributeClassificationQuery": "attributeClassificationQuery",
        }

    def fake_batch(llm_wrapper, requests, step, **kwargs):  # type: ignore[override]
        assert step == "pdpClassificationQuery"
        return [{"parent": {"finish": "N/A"}, "variants": {}}]

    monkeypatch.setattr(exporter, "get_naming_params", fake_get_naming_params)
    monkeypatch.setattr(exporter, "_run_pdp_llm_batch", fake_batch)

    parent_updated, variant_updated, llm_touched, _ = exporter._llm_fill_pdp_attributes(
        object(), parent_df, variant_df, taxonomy
    )
    assert variant_updated.is_empty()
    parent_row = parent_updated.row(0, named=True)
    assert parent_row["finish"] == "satin"
    assert llm_touched == {"parent": set(), "variant": set()}


def test_parse_pdp_response_handles_nested_batch_output() -> None:
    request = exporter._ParentLLMRequest(
        row_index=0,
        parent_product_id="P1",
        display_name="Prod",
        category_label="Lipstick",
        category_path="",
        deterministic_text="",
        pdp_text="",
        missing_attrs=["finish"],
        allowed_values={},
        nodes_by_label={},
        attr_column_map={"finish": "finish"},
        variants=[],
    )
    response = {
        "response": {
            "body": {
                "output": [
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": [
                                    {
                                        "type": "output_text",
                                        "text": '{"parent": {"finish": "matte"}, "variants": {}}',
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        }
    }

    parsed = exporter._parse_pdp_response(response, request)
    assert parsed["parent"]["finish"].value == "matte"
    assert parsed["variants"] == {}


def test_merge_attribute_values_coalesces_with_cast() -> None:
    base = pl.DataFrame(
        {
            "retailer": ["kiko"],
            "parent_product_id": ["P1"],
            "finish": [1],  # int dtype to provoke a cast mismatch
        }
    )
    persisted = pl.DataFrame(
        {
            "retailer": ["kiko"],
            "parent_product_id": ["P1"],
            "finish": ["matte"],  # Utf8 dtype
        }
    )

    merged = exporter._merge_attribute_values(
        base,
        persisted,
        left_on=["retailer", "parent_product_id"],
        right_on=["retailer", "parent_product_id"],
    )

    assert merged.get_column("finish").item() == "matte"
    assert merged.get_column("finish").dtype == pl.Utf8


def test_deserialize_frame_supports_list_columns() -> None:
    frame = pl.DataFrame(
        {
            "retailer": ["ulta"],
            "category_path": [["setting_spray_powder"]],
        }
    )

    payload = exporter._serialize_frame(frame)
    restored = exporter._deserialize_frame(payload)

    assert restored.height == 1
    assert restored.schema["category_path"] == pl.List(pl.Utf8)
    assert restored.get_column("category_path").to_list() == [["setting_spray_powder"]]


def test_apply_sure_consensus_to_frame_prefills_placeholder_columns() -> None:
    df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "finish": None,
                "performance claims": "N/A",
                "coverage": "medium",
            }
        ]
    )
    sure_consensus = pl.DataFrame(
        [
            {
                "row_type": "parent",
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "variant_id": "",
                "attribute_id": "finish",
                "consensus_value": "matte",
            },
            {
                "row_type": "parent",
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "variant_id": "",
                "attribute_id": "performance_claims",
                "consensus_value": "waterproof",
            },
            {
                "row_type": "parent",
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "variant_id": "",
                "attribute_id": "coverage",
                "consensus_value": "full",
            },
        ]
    )

    result, updates = exporter._apply_sure_consensus_to_frame(
        df,
        row_type="parent",
        sure_consensus=sure_consensus,
    )

    row = result.row(0, named=True)
    assert updates == 3
    assert row["finish"] == "matte"
    assert row["performance claims"] == "waterproof"
    # Meaningful value should not be overwritten by consensus.
    assert row["coverage"] == "medium"


def test_harmonize_parent_variant_attributes_sets_consensus() -> None:
    parent_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "finish": None,
            }
        ]
    )
    variant_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "finish": "matte",
            },
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "variant_id": "V2",
                "finish": "matte",
            },
        ]
    )

    result = exporter._harmonize_parent_variant_attributes(parent_df, variant_df)
    row = result.row(0, named=True)
    assert row["finish"] == "matte"


def test_harmonize_parent_variant_attributes_sets_na_when_values_differ() -> None:
    parent_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "finish": None,
            }
        ]
    )
    variant_df = pl.DataFrame(
        [
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "finish": "matte",
            },
            {
                "retailer": "Amazon",
                "parent_product_id": "P1",
                "variant_id": "V2",
                "finish": "satin",
            },
        ]
    )

    result = exporter._harmonize_parent_variant_attributes(parent_df, variant_df)
    row = result.row(0, named=True)
    assert row["finish"] == "N/A"


def test_harmonize_parent_variant_attributes_skips_permanent_suppressed_attrs() -> None:
    parent_df = pl.DataFrame(
        [
            {
                "retailer": "cosmoprofbeauty",
                "parent_product_id": "P1",
                "category_key": "permanent",
                "haircolor_level": None,
            }
        ]
    )
    variant_df = pl.DataFrame(
        [
            {
                "retailer": "cosmoprofbeauty",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "haircolor_level": "6-6",
            },
            {
                "retailer": "cosmoprofbeauty",
                "parent_product_id": "P1",
                "variant_id": "V2",
                "haircolor_level": "6-6",
            },
        ]
    )

    result = exporter._harmonize_parent_variant_attributes(parent_df, variant_df)
    row = result.row(0, named=True)

    assert row["haircolor_level"] is None


def test_normalize_cache_merge_key_columns_treats_null_parent_variant_as_empty() -> (
    None
):
    df = pl.DataFrame(
        {
            "record_type": ["parent", "parent"],
            "retailer": ["saksfifthavenue", "saksfifthavenue"],
            "product": ["0400020062502", "0400020062502"],
            "variant": [None, ""],
            "category_key": ["low_top_sneakers", "low_top_sneakers"],
        }
    )
    key_cols = ["record_type", "retailer", "product", "variant", "category_key"]

    normalized = exporter._normalize_cache_merge_key_columns(df, key_cols)

    assert normalized.get_column("variant").to_list() == ["", ""]
    assert normalized.unique(subset=key_cols).height == 1
