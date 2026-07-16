from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
TESTS_ROOT = ROOT / "tests"


def _under_tests(entry: str) -> bool:
    try:
        resolved = Path(entry).resolve()
    except Exception:
        return False
    return resolved == TESTS_ROOT or TESTS_ROOT in resolved.parents


filtered_path = [entry for entry in sys.path if not _under_tests(entry)]
if str(ROOT) not in filtered_path:
    filtered_path.insert(0, str(ROOT))
sys.path = filtered_path

brand_aliases = ROOT / "brand_aliases.json"
if not brand_aliases.exists():
    brand_aliases.write_text("{}", encoding="utf-8")

taxonomy_json = ROOT / "attribute_taxonomy.json"
if not taxonomy_json.exists():
    taxonomy_json.write_text(json.dumps({"categories": []}), encoding="utf-8")

import polars as pl
import pytest

import modules.add_attributes.attribute_taxonomy as attr_tax
import modules.add_attributes.attribute_classification as attr_cls
from modules.add_attributes.attribute_classification import (
    _deterministic_guess,
    _deterministic_multi_hits,
    _leaf_synonym_map,
    classify_attributes_for_products,
    classify_product_attributes,
    discover_objective_attributes_for_category,
)
from modules.add_attributes.normalization import normalize_product_key


@pytest.fixture()
def tmp_taxonomy(monkeypatch, tmp_path: Path) -> Path:
    """Point taxonomy helpers at a temporary JSON file."""
    tmp_json = tmp_path / "attribute_taxonomy.json"
    tmp_json.write_text(json.dumps({"categories": []}), encoding="utf-8")
    monkeypatch.setattr(attr_tax, "TAXONOMY_PATH", tmp_json)
    return tmp_json


@pytest.fixture()
def tmp_activity(monkeypatch, tmp_path: Path) -> Path:
    """Point attribute activity helpers at a temporary JSON file."""
    tmp_json = tmp_path / "attribute_activity.json"
    tmp_json.write_text(json.dumps({"categories": []}), encoding="utf-8")
    monkeypatch.setattr(attr_tax, "ATTRIBUTE_ACTIVITY_PATH", tmp_json)
    attr_tax.get_attribute_activity.cache_clear()
    yield tmp_json
    attr_tax.get_attribute_activity.cache_clear()


def test_discover_returns_taxonomy_deduped_when_category_exists(tmp_taxonomy: Path):
    # Arrange: taxonomy contains the category with three attributes
    data = {
        "categories": [
            {
                "id": "laptops",
                "attributes": [
                    {"label": "Weight"},
                    {"label": "Battery Life"},
                    {"label": "Color"},
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(data), encoding="utf-8")

    # Act
    out = discover_objective_attributes_for_category(
        llm_wrapper=None,
        category="Laptops",
        existing_columns=["color", "price"],
        throttle=0,
    )

    # Assert: lowercased, deduped against existing columns, preserves order
    assert out == ["weight", "battery life"]


def test_discover_missing_context_avoids_llm_calls(monkeypatch, tmp_taxonomy: Path):
    # Arrange: ensure LLM path would fail if called
    import modules.llm.batch_runner as batch_runner

    def fail_run_step_json(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("LLM should not be called when context is missing")

    monkeypatch.setattr(batch_runner, "run_step_json", fail_run_step_json)

    # Act
    out = discover_objective_attributes_for_category(
        llm_wrapper=None,
        category="unknown",
        existing_columns=[],
        throttle=0,
        context=None,  # missing industry/company
    )

    # Assert
    assert out == []


def test_discover_absent_category_calls_llm_and_persists(
    monkeypatch, tmp_taxonomy: Path
):
    # Arrange: stub LLM branch response; no dedup LLM needed (llm_wrapper=None)
    import modules.llm.batch_runner as batch_runner

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        # Return a full taxonomy branch
        return [
            {
                "id": "headphones",
                "label": "Headphones",
                "attributes": [
                    {"id": "imp", "label": "Impedance"},
                    {"id": "drv", "label": "Driver Size"},
                    {"id": "col", "label": "Color"},
                ],
            }
        ]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    # Act
    out = discover_objective_attributes_for_category(
        llm_wrapper=None,  # keep dedup local; avoid LLM in deduplicate step
        category="Headphones",
        existing_columns=["color"],
        throttle=0,
        context={"industry": "Consumer electronics"},
    )

    # Assert: returns new attributes (lowercased) excluding existing "color"
    assert sorted(out) == ["driver size", "impedance"]

    # And taxonomy file now contains the new branch
    saved = json.loads(tmp_taxonomy.read_text(encoding="utf-8"))
    ids = [str(c.get("id")).lower() for c in saved.get("categories", [])]
    assert "headphones" in ids


def test_classify_product_attributes_maps_and_lowercases(monkeypatch):
    # Arrange: stub LLM JSON classification
    import modules.llm.batch_runner as batch_runner

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        return [
            {
                "values": {
                    "Brand": {"value": "Apple"},
                    "color": {"value": "Black"},
                }
            }
        ]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    # Act
    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Test Phone",
        attributes=["Brand", "Color"],
    )

    # Assert: keys and values lowercased
    assert out == {"brand": "apple", "color": "black"}


def test_classify_product_attributes_enforces_allowed_values_and_domains(monkeypatch):
    # Arrange: capture tools argument and return a value that is not in taxonomy
    import modules.llm.batch_runner as batch_runner

    seen_tools = {}

    seen_tools = {}

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        seen_tools["tools"] = kwargs.get("tools")
        seen_tools["extra_body"] = kwargs.get("extra_body")
        return [{"values": {"color": {"value": "blue"}}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    # Act
    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["color"],
        allowed_values={"color": ["black", "white"]},
        domains=["example.com"],
    )

    # Assert: value clamped to "not in taxonomy" and tools restricted to the domain
    assert out == {"color": "not in taxonomy"}
    assert isinstance(seen_tools.get("tools"), list)
    assert seen_tools["tools"] == [
        {"type": "web_search", "filters": {"allowed_domains": ["example.com"]}}
    ]
    # Domain filtering is embedded in the tool; no extra_body required.
    body = seen_tools["extra_body"]
    assert body is None or body == {"include": ["web_search_call.action.sources"]}


def test_classify_product_attributes_can_disable_web_search(monkeypatch):
    import modules.llm.batch_runner as batch_runner

    captured: dict[str, object] = {}

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        captured["tools"] = kwargs.get("tools")
        captured["extra_body"] = kwargs.get("extra_body")
        captured["prompt"] = prompt
        return [{"values": {"color": {"value": "black"}}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["color"],
        allowed_values={"color": ["black", "white"]},
        domains=["example.com"],
        enable_web_search=False,
    )

    assert out == {"color": "black"}
    assert captured["tools"] is None
    assert captured["extra_body"] is None
    assert "Do not use web search" in str(captured["prompt"])


def test_classify_attributes_for_products_respects_requested_attr_subset(
    monkeypatch,
):
    taxonomy = {
        "categories": [
            {
                "id": "permanent",
                "label": "Permanent",
                "attributes": [
                    {"id": "benefit", "label": "Benefit"},
                    {"id": "haircolor_level", "label": "Haircolor Level"},
                ],
            }
        ]
    }

    monkeypatch.setattr(attr_cls, "normalize_all_categories", lambda: None)
    monkeypatch.setattr(attr_cls, "get_runtime_attribute_taxonomy", lambda: taxonomy)
    monkeypatch.setattr(attr_cls, "get_attribute_activity", lambda: {})
    monkeypatch.setattr(attr_cls, "load_cache", lambda: {})
    monkeypatch.setattr(attr_cls, "save_cache", lambda cache: None)
    monkeypatch.setattr(attr_cls, "load_alias_index", lambda: {})

    captured: dict[str, list[str]] = {}

    def fake_classify_product_attributes(
        llm_wrapper,
        product_name,
        attributes,
        **kwargs,
    ):
        captured["attributes"] = list(attributes)
        return {attr: f"{attr}_value" for attr in attributes}

    monkeypatch.setattr(
        attr_cls,
        "classify_product_attributes",
        fake_classify_product_attributes,
    )

    df = pl.DataFrame(
        [
            {
                "product_name": "Topchic Permanent Hair Color Tubes",
                "category_key": "permanent",
            }
        ]
    )

    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product_name",
        products=["Topchic Permanent Hair Color Tubes"],
        attr_map={"permanent": ["benefit"]},
        group_col="category_key",
        groups=["permanent"],
        deterministic_only=True,
    )

    assert captured["attributes"] == ["benefit"]
    assert "benefit" in out_df.columns
    assert "haircolor level" not in out_df.columns


def test_classify_product_attributes_alias_override_wins(monkeypatch):
    # Arrange: deterministic alias stage should respect explicit overrides
    import modules.llm.batch_runner as batch_runner

    def fail_run_step_json(*args, **kwargs):  # pragma: no cover - should not run
        raise AssertionError(
            "LLM should not be called when deterministic match succeeds"
        )

    monkeypatch.setattr(batch_runner, "run_step_json", fail_run_step_json)

    attr_nodes = {
        "finish": [
            {"label": "Glossy"},
            {"label": "Matte", "synonyms": ["Satin"]},
        ]
    }

    # Act
    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["finish"],
        allowed_values={"finish": ["glossy", "matte"]},
        attr_nodes=attr_nodes,
        attr_aliases={"finish": {"satin": "glossy"}},
        deterministic_text="Premium Satin Widget",
    )

    # Assert: override maps the conflicting alias to the desired canonical leaf
    assert out == {"finish": "glossy"}


def test_classify_product_attributes_prompt_places_rules_first(monkeypatch):
    import modules.llm.batch_runner as batch_runner

    captured: dict[str, str] = {}

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        captured["prompt"] = prompt
        return [{"values": {}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["color"],
        category="phones",
        allowed_values={"color": ["black", "white"]},
        domains=["example.com"],
    )

    prompt = captured["prompt"]
    assert prompt.startswith("Rules:\n")
    assert "Options (JSON):```json" in prompt
    assert "Context:\n" in prompt
    assert prompt.index("Context:\n") > prompt.index("Options (JSON)")
    assert prompt.index("Product: Widget.") > prompt.index("Context:\n")
    assert "Search only on: example.com." in prompt


def test_classify_product_attributes_prompt_orders_context_for_freeform(monkeypatch):
    import modules.llm.batch_runner as batch_runner

    captured: dict[str, str] = {}

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        captured["prompt"] = prompt
        return [{"values": {}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["color", "size"],
        category="phones",
        domains=["example.com"],
    )

    prompt = captured["prompt"]
    assert prompt.startswith("Rules:\n")
    assert "Context:\n" in prompt
    context = prompt.split("Context:\n", 1)[1]
    lines = context.splitlines()
    assert lines[0].startswith("Attributes: color, size.")
    assert any(line == "Product: Widget." for line in lines)
    assert lines[-1] == "Search only on: example.com."


def test_classify_product_attributes_uses_description_only_for_deterministic(
    monkeypatch,
):
    """The deterministic alias pass should see descriptions while the LLM does not."""

    import modules.llm.batch_runner as batch_runner

    def fail_run_step_json(*args, **kwargs):  # pragma: no cover - deterministic only
        raise AssertionError(
            "LLM should not be called when deterministic match succeeds"
        )

    monkeypatch.setattr(batch_runner, "run_step_json", fail_run_step_json)

    nodes = [{"label": "red", "synonyms": ["deep crimson"]}]

    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["color"],
        allowed_values={"color": ["red"]},
        attr_nodes={"color": nodes},
        deterministic_text="Widget. Description: Deep crimson finish",
    )

    assert out == {"color": "red"}


def test_classify_attributes_skips_inactive_attributes(
    monkeypatch, tmp_taxonomy: Path, tmp_activity: Path
):
    taxonomy_data = {
        "categories": [
            {
                "id": "foundation",
                "label": "Foundation",
                "attributes": [
                    {"id": "finish", "label": "Finish"},
                    {"id": "coverage", "label": "Coverage"},
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy_data), encoding="utf-8")

    activity_data = {
        "categories": [
            {
                "id": "foundation",
                "label": "Foundation",
                "attributes": [
                    {"id": "finish", "status": "active"},
                    {"id": "coverage", "status": "inactive"},
                ],
            }
        ]
    }
    tmp_activity.write_text(json.dumps(activity_data), encoding="utf-8")
    attr_tax.get_attribute_activity.cache_clear()

    df = pl.DataFrame({"product": ["Prod1"], "category": ["foundation"]})
    attr_map = {"foundation": ["finish", "coverage"]}

    parquet_path = tmp_taxonomy.parent / "classifications.parquet"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(attr_cls, "CLASSIFICATION_PARQUET", parquet_path)

    cache_payload = {
        "foundation": {"": {"prod1": {"finish": "matte", "coverage": "full"}}}
    }
    monkeypatch.setattr(attr_cls, "load_cache", lambda: cache_payload)
    monkeypatch.setattr(attr_cls, "save_cache", lambda *_a, **_k: None)

    result = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Prod1"],
        attr_map=attr_map,
        group_col="category",
        groups=["foundation"],
        deterministic_only=True,
    )

    assert "finish" in result.columns
    assert "coverage" in result.columns

    llm_result = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Prod1"],
        attr_map=attr_map,
        group_col="category",
        groups=["foundation"],
        deterministic_only=False,
        use_batch=False,
    )

    assert "coverage" not in llm_result.columns


def test_deterministic_guess_handles_punctuation_boundaries():
    alias_map = {"red": "red"}

    guess = _deterministic_guess("Color: Red.", alias_map)

    assert guess == "red"


def test_deterministic_guess_skips_hyphenated_substrings():
    alias_map = {"gel": "gel"}

    guess = _deterministic_guess("Texture: gel-like finish", alias_map)
    hits = _deterministic_multi_hits("Texture: gel-like finish", alias_map)

    assert guess is None
    assert hits == []


def test_leaf_synonym_map_skips_generic_oil_label_alias() -> None:
    alias_map = _leaf_synonym_map(
        [{"label": "oil", "synonyms": ["primer oil", "oil based", "dry oil"]}]
    )

    assert "oil" not in alias_map
    assert alias_map["primer oil"] == "oil"
    assert alias_map["oil based"] == "oil"
    assert alias_map["dry oil"] == "oil"


def test_deterministic_multi_hits_ignores_generic_oil_token_from_ingredients() -> None:
    alias_map = _leaf_synonym_map(
        [{"label": "oil", "synonyms": ["primer oil", "oil based", "dry oil"]}]
    )

    ingredient_hits = _deterministic_multi_hits(
        "Ingredients: Meadowfoam Seed Oil, Polyglycerin, Sodium Benzoate",
        alias_map,
    )
    explicit_hits = _deterministic_multi_hits(
        "This primer oil delivers a dry oil finish.",
        alias_map,
    )

    assert ingredient_hits == []
    assert explicit_hits == ["oil"]


@pytest.mark.parametrize(
    "text",
    [
        "Non vegan treat",  # space-separated prefix
        "anti vegan option",  # other negation prefix
        "No gluten ingredients",  # no + token
        "Not matte finish",  # explicit negation
        "Without dairy creamer",  # without + token
    ],
)
def test_deterministic_guess_skips_negated_prefix_tokens(text: str) -> None:
    alias_map = {
        "vegan": "vegan",
        "gluten": "gluten",
        "dairy": "dairy",
    }

    guess = _deterministic_guess(text, alias_map)
    hits = _deterministic_multi_hits(text, alias_map)

    assert guess is None
    assert hits == []


def test_classify_attributes_for_products_blocks_cross_attribute_ambiguous_aliases(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
) -> None:
    taxonomy = {
        "categories": [
            {
                "id": "face_primer",
                "label": "Face primer",
                "attributes": [
                    {
                        "id": "form",
                        "label": "Form",
                        "nodes": [
                            {"id": "oil", "label": "Oil", "synonyms": ["oil based"]}
                        ],
                    },
                    {
                        "id": "base_type",
                        "label": "Base type",
                        "nodes": [
                            {
                                "id": "oil_based",
                                "label": "Oil-based",
                                "synonyms": ["oil based"],
                            }
                        ],
                    },
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    monkeypatch.setattr(attr_cls, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")
    monkeypatch.setattr(attr_cls, "load_cache", lambda: {})
    monkeypatch.setattr(attr_cls, "save_cache", lambda *_a, **_k: None)

    df = pl.DataFrame(
        [
            {
                "product": "Primer",
                "category": "face_primer",
                "description": "Oil based smoothing primer",
            }
        ]
    )

    out = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Primer"],
        attr_map={},
        group_col="category",
        groups=["face_primer"],
        deterministic_only=True,
        desc_col="description",
    )

    row = out.row(0, named=True)
    assert row["form"] == "N/A"
    assert row["base type"] == "N/A"


@pytest.mark.parametrize(
    "text",
    [
        "Gluten free crust",  # trailing free token
        "Sugar free",  # trailing free token without extra words
        "Vegan free option",  # explicit free token following attribute
    ],
)
def test_deterministic_guess_skips_negated_suffix_tokens(text: str) -> None:
    alias_map = {
        "gluten": "gluten",
        "sugar": "sugar",
        "vegan": "vegan",
    }

    guess = _deterministic_guess(text, alias_map)
    hits = _deterministic_multi_hits(text, alias_map)

    assert guess is None
    assert hits == []


def test_classify_product_attributes_deterministic_multi_hits_use_taxonomy_order(
    monkeypatch,
):
    import modules.llm.batch_runner as batch_runner

    def fail_run_step_json(*args, **kwargs):  # pragma: no cover - deterministic only
        raise AssertionError(
            "LLM should not be called when deterministic match succeeds"
        )

    monkeypatch.setattr(batch_runner, "run_step_json", fail_run_step_json)

    attr_nodes = {"application areas": [{"label": "face"}, {"label": "under-eye"}]}

    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["application areas"],
        allowed_values={"application areas": ["face", "under-eye"]},
        attr_nodes=attr_nodes,
        deterministic_text="Apply on face and under-eye area",
        deterministic_only=True,
    )

    assert out == {"application areas": "face"}


def test_classify_product_attributes_llm_list_collapses_taxonomy_order(monkeypatch):
    import modules.llm.batch_runner as batch_runner

    def stub_run_step_json(*args, **kwargs):
        return [
            {
                "values": {
                    "application areas": {"value": ["under-eye", "face"]},
                }
            }
        ]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    attr_nodes = {"application areas": [{"label": "face"}, {"label": "under-eye"}]}

    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["application areas"],
        allowed_values={"application areas": ["face", "under-eye"]},
        attr_nodes=attr_nodes,
        deterministic_text="Widget",
    )

    assert out == {"application areas": "face"}


def test_classify_product_attributes_prompt_excludes_description(monkeypatch):
    import modules.llm.batch_runner as batch_runner

    captured: dict[str, str] = {}

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        captured["prompt"] = prompt
        return [{"values": {"color": {"value": "red"}}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    nodes = [{"label": "red"}]

    classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["color"],
        allowed_values={"color": ["red"]},
        attr_nodes={"color": nodes},
        deterministic_text="Widget. Description: extra context",
    )

    prompt = captured["prompt"]
    assert "Description: extra context" not in prompt
    assert "Product: Widget." in prompt


def test_classify_product_attributes_normalizes_na(monkeypatch):
    import modules.llm.batch_runner as batch_runner

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        return [{"values": {"color": "no idea"}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Widget",
        attributes=["color"],
        allowed_values={"color": ["red", "green"]},
    )

    assert out == {"color": "N/A"}


def test_classify_product_attributes_extracts_spf_deterministically_without_enum_nodes():
    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="Tinted Moisturizer",
        attributes=["spf"],
        deterministic_text="Tinted Moisturizer Broad Spectrum SPF 30",
        deterministic_only=True,
    )

    assert out == {"spf": "30"}


def test_classify_product_attributes_spf_ignores_unrelated_leading_numbers():
    out = classify_product_attributes(
        llm_wrapper=object(),
        product_name="4-in-1 Skin Tint",
        attributes=["spf"],
        deterministic_text="4-in-1 Skin Tint Mineral Sunscreen Broad Spectrum SPF 50",
        deterministic_only=True,
    )

    assert out == {"spf": "50"}


def test_classify_attributes_for_products_refreshes_cached_spf(monkeypatch):
    df = pl.DataFrame(
        {
            "product_name": [
                "4-in-1 Skin Tint Mineral Sunscreen Broad Spectrum SPF 50"
            ],
            "category_key": ["tinted_moisturizer"],
            "brand": ["PÜR Minerals"],
            "description": ["Mineral sunscreen skin tint with SPF 50."],
        }
    )
    stale_cache = {
        "tinted_moisturizer": {
            "pür minerals": {
                normalize_product_key(
                    "PÜR Minerals 4-in-1 Skin Tint Mineral Sunscreen Broad Spectrum SPF 50"
                ): {"spf": "4"}
            }
        }
    }

    monkeypatch.setattr(attr_cls, "load_cache", lambda: stale_cache)
    monkeypatch.setattr(attr_cls, "save_cache", lambda cache: None)

    out = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product_name",
        products=df.get_column("product_name").to_list(),
        attr_map={"tinted_moisturizer": ["spf"]},
        group_col="category_key",
        groups=df.get_column("category_key").to_list(),
        deterministic_only=True,
        brand_col="brand",
        desc_col="description",
    )

    row = out.row(0, named=True)
    assert row["spf"] == "50"


def test_classify_attributes_for_products_hierarchical_and_parquet(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    # Arrange: taxonomy with hierarchical attribute (levels=2)
    taxonomy = {
        "categories": [
            {
                "id": "phones",
                "attributes": [
                    {
                        "id": "mat",
                        "label": "Material",
                        "hierarchical": "true",
                        "levels": 2,
                        "nodes": [
                            {
                                "label": "body",
                                "children": [
                                    {"label": "aluminum"},
                                    {"label": "plastic"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    # Stub the classification to return a leaf value
    import modules.add_attributes.attribute_classification as ac

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        return {"material": "aluminum"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    # Redirect parquet writes to a temporary file
    parquet_path = tmp_path / "attribute_classifications.parquet"
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", parquet_path)

    df = pl.DataFrame(
        [{"product": "P1", "category": "phones"}],
        orient="row",
    )

    # Act
    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["P1"],
        attr_map={},
        group_col="category",
    )

    # Assert: both parent and child values are set; parquet is written
    assert out_df.height == 1
    row = out_df.row(0, named=True)
    assert row["material_children"] == "aluminum"
    assert row["material"] == "body"
    assert parquet_path.is_file()


def test_classify_attributes_for_products_recovers_corrupt_parquet_cache(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    taxonomy = {
        "categories": [
            {
                "id": "phones",
                "attributes": [
                    {
                        "label": "Color",
                        "nodes": [{"label": "red"}, {"label": "green"}],
                    }
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    import modules.add_attributes.attribute_classification as ac

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        return {"color": "red"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    parquet_path = tmp_path / "cls.parquet"
    parquet_path.write_text("not parquet", encoding="utf-8")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", parquet_path)

    df = pl.DataFrame([{"product": "P1", "category": "phones"}])
    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["P1"],
        attr_map={},
        group_col="category",
    )

    assert out_df.height == 1
    assert out_df.row(0, named=True)["color"] == "red"
    assert parquet_path.is_file()
    reloaded = pl.read_parquet(parquet_path)
    assert reloaded.height == 1
    broken_files = list(tmp_path.glob("cls.corrupt_*.parquet"))
    assert broken_files


def test_classify_attributes_for_products_keeps_na(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    taxonomy = {
        "categories": [
            {
                "id": "phones",
                "attributes": [
                    {
                        "label": "Color",
                        "nodes": [{"label": "red"}, {"label": "green"}],
                    }
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        return {"color": "n/a"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    df = pl.DataFrame([{"product": "P1", "category": "phones"}])

    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["P1"],
        attr_map={},
        group_col="category",
    )

    row = out_df.row(0, named=True)
    assert row["color"] == "N/A"


def test_classify_attributes_for_products_retries_without_domains(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    taxonomy = {
        "categories": [
            {
                "id": "phones",
                "attributes": [
                    {
                        "label": "Color",
                        "nodes": [{"label": "red"}, {"label": "green"}],
                    }
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    calls: list[dict[str, Any]] = []

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        calls.append(
            {
                "name": product_name,
                "domains": kwargs.get("domains"),
                "deterministic_text": kwargs.get("deterministic_text"),
            }
        )
        if kwargs.get("domains") is None:
            if "Widget" in product_name:
                return {"color": "red"}
            if "Gadget" in product_name:
                return {"color": "green"}
        return {"color": "N/A"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    df = pl.DataFrame(
        [
            {
                "sku": "Widget",
                "category": "phones",
                "brand": "Acme",
                "description": "Compact phone",
            },
            {
                "sku": "Gadget",
                "category": "phones",
                "brand": "Zen",
                "description": "Large phone",
            },
        ]
    )

    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="sku",
        products=["Widget", "Gadget"],
        attr_map={},
        group_col="category",
        domains_map={
            "widget": ["https://acme.com"],
            "gadget": ["https://zen.com"],
        },
        brand_col="brand",
        desc_col="description",
    )

    assert [call["domains"] for call in calls] == [
        ["https://acme.com"],
        ["https://zen.com"],
        None,
        None,
    ]
    assert calls[0]["name"] == "Acme Widget"
    assert calls[1]["name"] == "Zen Gadget"
    assert calls[2]["name"] == "Acme Widget"
    assert calls[3]["name"] == "Zen Gadget"
    assert calls[0]["deterministic_text"] == "Acme Widget. Description: Compact phone"
    assert calls[1]["deterministic_text"] == "Zen Gadget. Description: Large phone"
    assert calls[2]["deterministic_text"] == "Acme Widget. Description: Compact phone"
    assert calls[3]["deterministic_text"] == "Zen Gadget. Description: Large phone"

    row_widget = out_df.filter(pl.col("sku") == "Widget").row(0, named=True)
    row_gadget = out_df.filter(pl.col("sku") == "Gadget").row(0, named=True)
    assert row_widget["color"] == "red"
    assert row_gadget["color"] == "green"


def test_classify_attributes_for_products_logs_unmapped(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    taxonomy = {
        "categories": [
            {
                "id": "phones",
                "attributes": [
                    {
                        "label": "Color",
                        "nodes": [{"label": "red"}, {"label": "green"}],
                    }
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    queued: list[dict] = []

    def stub_queue(entry):
        queued.append(entry)

    monkeypatch.setattr(ac, "queue_taxonomy_review", stub_queue)

    novelties: list[dict] = []

    def stub_novelty(**kwargs):
        novelties.append(kwargs)

    monkeypatch.setattr(ac, "append_novelty", stub_novelty)

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        return {"color": "blue"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    df = pl.DataFrame([{"product": "P1", "category": "phones"}])

    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["P1"],
        attr_map={},
        group_col="category",
    )

    row = out_df.row(0, named=True)
    assert row["color"] == "not in taxonomy"
    assert queued == [
        {"category": "phones", "attribute": "color", "value": "blue", "product": "P1"}
    ]
    assert novelties == [
        {
            "category": "phones",
            "attribute": "color",
            "raw_value": "blue",
            "product": "P1",
            "source": "llm_inferred",
        }
    ]


def test_classify_attributes_for_products_normalizes_explicit_taxonomy_labels(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
) -> None:
    taxonomy = {
        "categories": [
            {
                "id": "lipstick",
                "attributes": [
                    {
                        "id": "finish",
                        "label": "Finish",
                        "nodes": [
                            {"id": "cream", "label": "cream finish"},
                            {"id": "sheer", "label": "sheer finish"},
                        ],
                    },
                    {
                        "id": "coverage",
                        "label": "Coverage",
                        "nodes": [{"id": "sheer", "label": "sheer coverage"}],
                    },
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        return {"finish": "cream", "coverage": "sheer"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    df = pl.DataFrame([{"product": "P1", "category": "lipstick"}])

    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["P1"],
        attr_map={},
        group_col="category",
    )

    row = out_df.row(0, named=True)
    assert row["finish"] == "cream finish"
    assert row["coverage"] == "sheer coverage"


def test_classify_attributes_for_products_invalid_product_skipped(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    # Arrange: no taxonomy match and invalid product name
    import modules.add_attributes.attribute_classification as ac

    tmp_taxonomy.write_text(json.dumps({"categories": []}), encoding="utf-8")
    parquet_path = tmp_path / "attribute_classifications.parquet"
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", parquet_path)

    df = pl.DataFrame(
        [{"product": "N/A", "category": "misc"}],
        orient="row",
    )

    # Act
    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["N/A"],
        attr_map={},
        group_col="category",
    )

    # Assert: invalid product skipped; nothing written
    assert out_df.height == 0
    assert not parquet_path.exists()


def test_classify_attributes_for_products_uses_cache(monkeypatch, tmp_path: Path):
    """Second call reuses cached attributes instead of invoking LLM."""
    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    call_count = {"n": 0}

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        call_count["n"] += 1
        return {"color": "red"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    df = pl.DataFrame([{"product": "Widget"}])
    attr_map = {"All products": ["color"]}

    classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Widget"],
        attr_map=attr_map,
        use_batch=False,
    )

    assert call_count["n"] == 1
    cache_mapping = pac.load_cache()
    assert cache_mapping["all products"][""]["widget"]["color"] == "red"

    classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Widget"],
        attr_map=attr_map,
        use_batch=False,
    )

    assert call_count["n"] == 1


def test_classify_attributes_for_products_refreshes_placeholder_cache(
    monkeypatch, tmp_path: Path
):
    """Cached placeholder values are reprocessed by the deterministic pass."""

    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    cache_path = tmp_path / "product_attributes.json"
    parquet_path = tmp_path / "cls.parquet"
    monkeypatch.setattr(pac, "CACHE_FILE", cache_path)
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", parquet_path)

    pac.save_cache(
        {
            "all products": {
                "": {"widget": {"form": "N/A (not stated)"}},
            }
        }
    )

    call_count = {"n": 0}

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        call_count["n"] += 1
        return {"form": "liquid"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    df = pl.DataFrame([{"product": "Widget"}])
    attr_map = {"All products": ["form"]}

    out = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Widget"],
        attr_map=attr_map,
        use_batch=False,
    )

    assert call_count["n"] == 1
    assert out.row(0, named=True)["form"] == "liquid"

    cache_mapping = pac.load_cache()
    assert cache_mapping["all products"][""]["widget"]["form"] == "liquid"


def test_classify_attributes_for_products_expands_cache(monkeypatch, tmp_path: Path):
    """Requesting new attributes triggers additional classification calls."""
    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    call_count = {"n": 0}

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        call_count["n"] += 1
        return {a: f"{a}_val" for a in attributes}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    df = pl.DataFrame([{"product": "Widget"}])

    classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Widget"],
        attr_map={"All products": ["color"]},
        use_batch=False,
    )

    assert call_count["n"] == 1

    classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Widget"],
        attr_map={"All products": ["color", "size"]},
        use_batch=False,
    )

    assert call_count["n"] == 2
    cache_mapping = pac.load_cache()
    assert cache_mapping["all products"][""]["widget"]["size"] == "size_val"


def test_classify_attributes_for_products_canonicalizes_product_keys(
    monkeypatch, tmp_path: Path
) -> None:
    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    call_count = {"n": 0}

    def stub_classify_product_attributes(
        llm_wrapper, product_name, attributes, **kwargs
    ):
        call_count["n"] += 1
        return {"color": "red"}

    monkeypatch.setattr(
        ac, "classify_product_attributes", stub_classify_product_attributes
    )

    df = pl.DataFrame(
        [
            {"product": "Widget 100ml"},
            {"product": "Widget 100 mL"},
        ]
    )

    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="product",
        products=["Widget 100ml", "Widget 100 mL"],
        attr_map={"All products": ["color"]},
        use_batch=False,
    )

    assert call_count["n"] == 1
    assert out_df.height == 2
    assert set(out_df["product"].to_list()) == {"Widget 100ml", "Widget 100 mL"}
    assert set(out_df["color"].to_list()) == {"red"}

    cache_mapping = pac.load_cache()
    norm_key = normalize_product_key("Widget 100ml")
    assert cache_mapping["all products"][""][norm_key]["color"] == "red"


def test_classify_attributes_for_products_reuses_alias_index(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
) -> None:
    """Deterministic alias resolution uses a preloaded alias index once per run."""

    taxonomy = {
        "categories": [
            {
                "id": "wines",
                "attributes": [
                    {
                        "id": "style",
                        "label": "Style",
                        "nodes": [
                            {"label": "Champagne"},
                            {"label": "Still"},
                        ],
                    }
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    import modules.add_attributes.attribute_classification as ac
    from src import product_attribute_cache as pac

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "cls.parquet")

    alias_calls = {"count": 0}

    alias_index = {
        "categories": {
            "wines": {"attributes": {"style": {"aliases": {"sparkling": "champagne"}}}}
        }
    }

    def stub_load_alias_index() -> dict[str, Any]:
        alias_calls["count"] += 1
        return alias_index

    monkeypatch.setattr(ac, "load_alias_index", stub_load_alias_index)

    df = pl.DataFrame(
        [
            {"name": "Sparkling Star", "category": "Wines"},
            {"name": "Sparkling Moon", "category": "Wines"},
        ]
    )

    out_df = classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="name",
        products=["Sparkling Star", "Sparkling Moon"],
        attr_map={"Wines": ["style"]},
        group_col="category",
        deterministic_only=True,
    )

    assert alias_calls["count"] == 1

    for product in ("Sparkling Star", "Sparkling Moon"):
        row = out_df.filter(pl.col("name") == product).row(0, named=True)
        assert row["style"] == "champagne"


def test_classify_attributes_for_products_buckets_share_prompt_prefix(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    import modules.add_attributes.attribute_classification as ac
    import modules.llm.batch_runner as batch_runner
    from src import product_attribute_cache as pac

    taxonomy = {
        "categories": [
            {
                "id": "makeup",
                "attributes": [
                    {
                        "label": "Finish",
                        "nodes": [
                            {"label": "matte", "synonyms": ["matte"]},
                            {"label": "dewy"},
                        ],
                    },
                    {
                        "label": "Coverage",
                        "nodes": [
                            {"label": "light"},
                            {"label": "medium"},
                            {"label": "full"},
                        ],
                    },
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "attr.parquet")
    monkeypatch.setattr(ac, "load_alias_index", lambda: {})

    prompts: list[str] = []

    def stub_run_step_json(
        llm_wrapper, step, system_prompt, prompt, **kwargs
    ) -> list[dict[str, Any]]:
        prompts.append(prompt)
        return [{"values": {"coverage": {"value": "full"}}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    df = pl.DataFrame(
        [
            {"product": "Matte Glow Foundation", "category": "makeup"},
            {"product": "Matte Finish Powder", "category": "makeup"},
        ],
        orient="row",
    )

    classify_attributes_for_products(
        llm_wrapper=object(),
        df=df,
        product_col="product",
        products=["Matte Glow Foundation", "Matte Finish Powder"],
        attr_map={},
        group_col="category",
    )

    assert len(prompts) == 2
    first_prefix = prompts[0].split("Context:", 1)[0]
    second_prefix = prompts[1].split("Context:", 1)[0]
    assert first_prefix == second_prefix


def test_classify_attributes_for_products_fallback_prompts_share_prefix(
    monkeypatch, tmp_taxonomy: Path, tmp_path: Path
):
    import modules.add_attributes.attribute_classification as ac
    import modules.llm.batch_runner as batch_runner
    from src import product_attribute_cache as pac

    taxonomy = {
        "categories": [
            {
                "id": "makeup",
                "attributes": [
                    {
                        "label": "Finish",
                        "nodes": [
                            {"id": "finish_matte", "label": "matte"},
                            {"id": "finish_dewy", "label": "dewy"},
                        ],
                    }
                ],
            }
        ]
    }
    tmp_taxonomy.write_text(json.dumps(taxonomy), encoding="utf-8")

    monkeypatch.setattr(pac, "CACHE_FILE", tmp_path / "product_attributes.json")
    monkeypatch.setattr(ac, "CLASSIFICATION_PARQUET", tmp_path / "attr.parquet")
    monkeypatch.setattr(ac, "load_alias_index", lambda: {})
    monkeypatch.setattr(
        ac,
        "get_run_params",
        lambda: {"attrClassificationRetryUnknowns": True},
    )

    fallback_prompts: list[str] = []

    def stub_run_step_json(llm_wrapper, step, system_prompt, prompt, **kwargs):
        if kwargs.get("extra_body"):
            return [{"values": {"finish": {"value": "unknown"}}}]

        fallback_prompts.append(prompt)
        product_line = next(
            (line for line in prompt.splitlines() if line.startswith("Product: ")), ""
        )
        value = "matte" if "Serum" in product_line else "dewy"
        return [{"values": {"finish": {"value": value}}}]

    monkeypatch.setattr(batch_runner, "run_step_json", stub_run_step_json)

    df = pl.DataFrame(
        [
            {"product": "Radiant Serum", "category": "makeup"},
            {"product": "Radiant Balm", "category": "makeup"},
        ],
        orient="row",
    )

    out_df = classify_attributes_for_products(
        llm_wrapper=object(),
        df=df,
        product_col="product",
        products=["Radiant Serum", "Radiant Balm"],
        attr_map={},
        group_col="category",
        use_batch=False,
        domains_map={
            "radiant serum": ["serum.example"],
            "radiant balm": ["balm.example"],
        },
    )

    assert len(fallback_prompts) == 2

    def prefix_through_options(prompt: str) -> str:
        marker = "Options (JSON):"
        start = prompt.index(marker)
        first_ticks = prompt.index("```", start)
        second_ticks = prompt.index("```", first_ticks + 3)
        return prompt[: second_ticks + 3]

    shared_prefix = prefix_through_options(fallback_prompts[0])
    for prompt in fallback_prompts[1:]:
        assert prefix_through_options(prompt) == shared_prefix

    serum_row = out_df.filter(pl.col("product") == "Radiant Serum").row(0, named=True)
    balm_row = out_df.filter(pl.col("product") == "Radiant Balm").row(0, named=True)
    assert serum_row["finish"] == "matte"
    assert balm_row["finish"] == "dewy"
