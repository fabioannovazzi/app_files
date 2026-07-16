from __future__ import annotations

import json

import polars as pl

from modules.pdp.attribute_mapping_core import (
    _apply_sure_consensus_values,
    _collect_parent_fill_audit,
    _collect_resolution_history_rows,
    _collect_resolution_snapshot_rows,
    _collect_web_audit,
    _load_existing_resolution_run_keys,
    _load_no_value_query_suppression,
    _load_resolution_tracked_keys,
)
from modules.pdp.store import AttributeAuditRecord


def test_collect_resolution_history_rows_maps_steps_and_context() -> None:
    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "variant_id": "V1",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
            }
        ]
    )
    records = [
        AttributeAuditRecord(
            timestamp="2026-02-01T00:00:00Z",
            source="cross_retailer_fill",
            row_type="variant",
            retailer="sephora",
            parent_product_id="P1",
            variant_id="V1",
            attribute_id="coverage",
            value="light",
            decision_rule="cross_retailer_fill",
            evidence_json=json.dumps({"rule": "priority"}),
            category_key=None,
        ),
        AttributeAuditRecord(
            timestamp="2026-02-01T00:01:00Z",
            source="vision",
            row_type="parent",
            retailer="sephora",
            parent_product_id="P1",
            variant_id="",
            attribute_id="finish",
            value="matte",
            decision_rule="vision_confident",
            evidence_json=json.dumps({"confidence": 0.91}),
            category_key="lipstick",
        ),
        AttributeAuditRecord(
            timestamp="2026-02-01T00:02:00Z",
            source="web",
            row_type="parent",
            retailer="sephora",
            parent_product_id="P1",
            variant_id="",
            attribute_id="base",
            value="silicone-based",
            decision_rule="web_confident",
            evidence_json=json.dumps(
                {
                    "confidence": 0.95,
                    "evidence_url": "https://brand.example/product",
                }
            ),
            category_key="lipstick",
        ),
    ]

    rows = _collect_resolution_history_rows(
        records,
        parents_df=parents_df,
        variants_df=variants_df,
        run_id="run-1",
    )

    assert len(rows) == 3
    cross_retailer = next(row for row in rows if row["attribute_id"] == "coverage")
    assert cross_retailer["step"] == "cross_retailer_fill"
    assert cross_retailer["canonical_id"] == "canon-1"
    assert cross_retailer["confidence"] is None
    assert cross_retailer["evidence_url"] is None

    vision = next(row for row in rows if row["attribute_id"] == "finish")
    assert vision["step"] == "vision"
    assert vision["confidence"] == 0.91
    assert vision["evidence_url"] is None

    web = next(row for row in rows if row["attribute_id"] == "base")
    assert web["step"] == "brand_web_search"
    assert web["confidence"] == 0.95
    assert web["evidence_url"] == "https://brand.example/product"


def test_collect_resolution_snapshot_rows_adds_meaningful_run_level_votes() -> None:
    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "finish": "matte",
                "coverage": "N/A",
            },
            {
                "retailer": "sephora",
                "parent_product_id": "P2",
                "canonical_id": "canon-2",
                "category_key": "lipstick",
                "finish": "dewy",
                "coverage": "N/A",
            },
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "finish": "N/A",
                "coverage": "light",
            }
        ]
    )
    meta_by_id = {
        "finish": {"id": "finish", "label": "Finish", "scope": "product"},
        "coverage": {"id": "coverage", "label": "Coverage", "scope": "variant"},
    }
    skip_keys = {
        ("parent", "sephora", "P2", "", "canon-2", "lipstick", "finish"),
    }

    rows = _collect_resolution_snapshot_rows(
        parents_df=parents_df,
        variants_df=variants_df,
        meta_by_id=meta_by_id,
        run_id="run-1",
        skip_keys=skip_keys,
    )

    assert len(rows) == 2
    keys = {
        (
            row["row_type"],
            row["retailer"],
            row["parent_product_id"],
            row["variant_id"],
            row["attribute_id"],
            row["value"],
        )
        for row in rows
    }
    assert ("parent", "sephora", "P1", "", "finish", "matte") in keys
    assert ("variant", "sephora", "P1", "V1", "coverage", "light") in keys
    for row in rows:
        assert row["run_id"] == "run-1"
        assert row["step"] == "run_snapshot"
        assert row["source"] == "snapshot"
        assert row["decision_rule"] == "snapshot_current_value"


def test_collect_resolution_snapshot_rows_respects_allowed_keys() -> None:
    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "finish": "matte",
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "coverage": "light",
            }
        ]
    )
    meta_by_id = {
        "finish": {"id": "finish", "label": "Finish", "scope": "product"},
        "coverage": {"id": "coverage", "label": "Coverage", "scope": "variant"},
    }
    allowed_keys = {
        ("parent", "sephora", "P1", "", "canon-1", "lipstick", "finish"),
    }

    rows = _collect_resolution_snapshot_rows(
        parents_df=parents_df,
        variants_df=variants_df,
        meta_by_id=meta_by_id,
        run_id="run-2",
        allowed_keys=allowed_keys,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["row_type"] == "parent"
    assert row["attribute_id"] == "finish"
    assert row["value"] == "matte"


def test_load_existing_resolution_run_keys_ignores_no_value_rows(
    tmp_path,
    monkeypatch,
) -> None:
    import modules.pdp.attribute_mapping_core as mapping_mod

    ledger_dir = tmp_path / "attribute_resolution_ledger"
    read_resolution_ledger = (
        mapping_mod.attribute_resolution_history.read_resolution_ledger
    )
    mapping_mod.attribute_resolution_history.append_resolution_ledger_rows(
        [
            {
                "run_id": "run-1",
                "recorded_at": "2026-02-12T10:00:00+00:00",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_confident",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "attribute_id": "finish",
                "value": "matte",
                "confidence": 0.95,
                "evidence_url": "https://example.com",
            },
            {
                "run_id": "run-1",
                "recorded_at": "2026-02-12T10:01:00+00:00",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P2",
                "variant_id": "",
                "canonical_id": "canon-2",
                "category_key": "lipstick",
                "attribute_id": "finish",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
        ],
        ledger_dir=ledger_dir,
    )
    monkeypatch.setattr(
        mapping_mod.attribute_resolution_history,
        "read_resolution_ledger",
        lambda: read_resolution_ledger(ledger_dir=ledger_dir),
    )

    keys = _load_existing_resolution_run_keys("run-1")
    assert ("parent", "sephora", "P1", "", "canon-1", "lipstick", "finish") in keys
    assert ("parent", "sephora", "P2", "", "canon-2", "lipstick", "finish") not in keys


def test_load_resolution_tracked_keys_ignores_no_value_rows(
    tmp_path,
    monkeypatch,
) -> None:
    import modules.pdp.attribute_mapping_core as mapping_mod

    ledger_dir = tmp_path / "attribute_resolution_ledger"
    read_resolution_ledger = (
        mapping_mod.attribute_resolution_history.read_resolution_ledger
    )
    mapping_mod.attribute_resolution_history.append_resolution_ledger_rows(
        [
            {
                "run_id": "run-1",
                "recorded_at": "2026-02-12T10:00:00+00:00",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_confident",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "attribute_id": "finish",
                "value": "matte",
                "confidence": 0.95,
                "evidence_url": "https://example.com",
            },
            {
                "run_id": "run-2",
                "recorded_at": "2026-02-12T10:01:00+00:00",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P2",
                "variant_id": "",
                "canonical_id": "canon-2",
                "category_key": "lipstick",
                "attribute_id": "finish",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
        ],
        ledger_dir=ledger_dir,
    )
    monkeypatch.setattr(
        mapping_mod.attribute_resolution_history,
        "read_resolution_ledger",
        lambda: read_resolution_ledger(ledger_dir=ledger_dir),
    )

    keys = _load_resolution_tracked_keys()
    assert ("parent", "sephora", "P1", "", "canon-1", "lipstick", "finish") in keys
    assert ("parent", "sephora", "P2", "", "canon-2", "lipstick", "finish") not in keys


def test_apply_sure_consensus_values_prefills_placeholders_only(monkeypatch) -> None:
    import modules.pdp.attribute_mapping_core as mapping_mod

    parents_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "finish": None,
                "coverage": "medium",
            }
        ]
    )
    variants_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "coverage": "N/A",
            }
        ]
    )
    consensus_df = pl.DataFrame(
        [
            {
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "attribute_id": "finish",
                "consensus_value": "matte",
                "support_runs": 3,
                "total_runs": 3,
                "agreement_rate": 1.0,
                "step_count": 1,
                "supporting_steps": ["llm_pdp_lookup"],
                "certainty_class": "sure",
                "max_confidence": None,
                "last_seen_at": "2026-02-01T00:00:00Z",
                "last_recorded_at": "2026-02-01T00:00:00Z",
            },
            {
                "row_type": "variant",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "attribute_id": "coverage",
                "consensus_value": "light",
                "support_runs": 3,
                "total_runs": 3,
                "agreement_rate": 1.0,
                "step_count": 1,
                "supporting_steps": ["brand_web_search"],
                "certainty_class": "sure",
                "max_confidence": 0.95,
                "last_seen_at": "2026-02-01T00:00:00Z",
                "last_recorded_at": "2026-02-01T00:00:00Z",
            },
            {
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "lipstick",
                "attribute_id": "coverage",
                "consensus_value": "full",
                "support_runs": 2,
                "total_runs": 2,
                "agreement_rate": 1.0,
                "step_count": 1,
                "supporting_steps": ["deterministic"],
                "certainty_class": "uncertain",
                "max_confidence": None,
                "last_seen_at": "2026-02-01T00:00:00Z",
                "last_recorded_at": "2026-02-01T00:00:00Z",
            },
        ]
    )
    monkeypatch.setattr(
        mapping_mod.attribute_resolution_history,
        "read_resolution_consensus",
        lambda: consensus_df,
    )

    out_parents, out_variants, parent_updates, variant_updates = (
        _apply_sure_consensus_values(
            parents_df,
            variants_df,
            meta_by_id={
                "finish": {"label": "Finish"},
                "coverage": {"label": "Coverage"},
            },
        )
    )

    assert parent_updates == 1
    assert variant_updates == 1
    assert out_parents.get_column("finish").item() == "matte"
    # Existing meaningful values are preserved.
    assert out_parents.get_column("coverage").item() == "medium"
    assert out_variants.get_column("coverage").item() == "light"


def test_collect_web_audit_includes_no_value_attempts() -> None:
    audit_df = pl.DataFrame(
        [
            {
                "category_key": "eyeliner",
                "source_retailer": "sephora",
                "source_parent_product_id": "P1",
                "requested_parent_attributes": "base, finish",
                "requested_variant_attributes": json.dumps(
                    {"sephora:V1": ["coverage", "shade_type"]}
                ),
                "filled_parent_attributes": json.dumps(
                    {
                        "base": {
                            "value": "silicone-based",
                            "confidence": 0.92,
                            "evidence_url": "https://brand.example/p",
                        }
                    }
                ),
                "filled_variant_attributes": json.dumps(
                    {
                        "sephora:V1": {
                            "coverage": {
                                "value": "medium",
                                "confidence": 0.9,
                                "evidence_url": "https://brand.example/p",
                            }
                        }
                    }
                ),
            }
        ]
    )

    records = _collect_web_audit(audit_df)

    by_key = {
        (
            record.row_type,
            record.retailer,
            record.parent_product_id,
            record.variant_id,
            record.attribute_id,
        ): record
        for record in records
    }
    assert len(records) == 4

    parent_filled = by_key[("parent", "sephora", "P1", "", "base")]
    assert parent_filled.value == "silicone-based"
    assert parent_filled.decision_rule == "web_confident"

    parent_unresolved = by_key[("parent", "sephora", "P1", "", "finish")]
    assert parent_unresolved.value is None
    assert parent_unresolved.decision_rule == "web_no_value"

    variant_filled = by_key[("variant", "sephora", "P1", "V1", "coverage")]
    assert variant_filled.value == "medium"
    assert variant_filled.decision_rule == "web_confident"

    variant_unresolved = by_key[("variant", "sephora", "P1", "V1", "shade_type")]
    assert variant_unresolved.value is None
    assert variant_unresolved.decision_rule == "web_no_value"


def test_collect_parent_fill_audit_tracks_placeholder_to_value_updates() -> None:
    before_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "finish": "N/A",
                "form": "powder",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "finish": "matte",
                "form": "powder",
            },
        ]
    )
    after_df = pl.DataFrame(
        [
            {
                "retailer": "sephora",
                "parent_product_id": "P1",
                "finish": "matte",
                "form": "powder",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "finish": "matte",
                "form": "powder",
            },
        ]
    )

    records = _collect_parent_fill_audit(
        before_df,
        after_df,
        ["finish", "form"],
        decision_rule="cross_retailer_fill",
        evidence={"retailer_priority": ["ulta", "sephora"]},
    )

    assert len(records) == 1
    record = records[0]
    assert record.row_type == "parent"
    assert record.retailer == "sephora"
    assert record.parent_product_id == "P1"
    assert record.variant_id == ""
    assert record.attribute_id == "finish"
    assert record.value == "matte"
    assert record.decision_rule == "cross_retailer_fill"


def test_load_no_value_query_suppression_uses_recent_run_window(monkeypatch) -> None:
    import modules.pdp.attribute_mapping_core as mapping_mod

    ledger_df = pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "recorded_at": "2026-02-01T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "finish",
                "value": "matte",
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-2",
                "recorded_at": "2026-02-02T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "finish",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-3",
                "recorded_at": "2026-02-03T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "finish",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-4",
                "recorded_at": "2026-02-04T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "finish",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-5",
                "recorded_at": "2026-02-05T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "finish",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-6",
                "recorded_at": "2026-02-06T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "finish",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-1",
                "recorded_at": "2026-02-01T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "base",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-2",
                "recorded_at": "2026-02-02T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "base",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-3",
                "recorded_at": "2026-02-03T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "base",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-4",
                "recorded_at": "2026-02-04T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "base",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-5",
                "recorded_at": "2026-02-05T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_confident",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "base",
                "value": "silicone-based",
                "confidence": 0.91,
                "evidence_url": "https://brand.example/p",
            },
            {
                "run_id": "run-2",
                "recorded_at": "2026-02-02T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "variant",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "coverage",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-3",
                "recorded_at": "2026-02-03T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "variant",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "coverage",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-4",
                "recorded_at": "2026-02-04T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "variant",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "coverage",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-5",
                "recorded_at": "2026-02-05T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "variant",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "coverage",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
            {
                "run_id": "run-6",
                "recorded_at": "2026-02-06T00:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_no_value",
                "row_type": "variant",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "V1",
                "canonical_id": "canon-1",
                "category_key": "eyeliner",
                "attribute_id": "coverage",
                "value": None,
                "confidence": None,
                "evidence_url": None,
            },
        ]
    )
    monkeypatch.setattr(
        mapping_mod.attribute_resolution_history,
        "read_resolution_ledger",
        lambda: ledger_df,
    )

    parent_blocked, variant_blocked = _load_no_value_query_suppression(
        step="brand_web_search",
        min_runs=5,
    )

    assert ("sephora", "P1", "finish") in parent_blocked
    assert ("sephora", "P1", "base") not in parent_blocked
    assert ("sephora", "V1", "coverage") in variant_blocked
