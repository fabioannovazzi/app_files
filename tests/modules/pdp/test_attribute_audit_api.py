from __future__ import annotations

from pathlib import Path

import modules.pdp.api as api_mod


def test_attach_attribute_audit_uses_explicit_audit_rows(monkeypatch) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return [
                {
                    "timestamp": "2026-02-09T00:00:00Z",
                    "source": "web",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "web_confident",
                    "evidence_json": '{"confidence": 0.95}',
                    "category_key": "concealer",
                }
            ]

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            raise AssertionError(
                "Stage fallback should not run when explicit audit exists."
            )

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": "natural",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "web"
    assert attached["decision_rule"] == "web_confident"
    assert attached["evidence"]["confidence"] == 0.95


def test_attach_attribute_audit_prefers_explicit_row_matching_current_value(
    monkeypatch,
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return [
                {
                    "timestamp": "2026-02-09T02:00:00Z",
                    "source": "web",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": None,
                    "decision_rule": "web_no_value",
                    "evidence_json": "{}",
                    "category_key": "concealer",
                },
                {
                    "timestamp": "2026-02-09T01:00:00Z",
                    "source": "deterministic",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "deterministic_text_match",
                    "evidence_json": '{"tiebreak":"taxonomy_order"}',
                    "category_key": "concealer",
                },
            ]

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            raise AssertionError(
                "Stage fallback should not run when explicit audit exists."
            )

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": "natural",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "deterministic"
    assert attached["decision_rule"] == "deterministic_text_match"
    assert attached["value"] == "natural"


def test_attach_attribute_audit_missing_current_value_uses_latest_row(monkeypatch) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return [
                {
                    "timestamp": "2026-02-09T02:00:00Z",
                    "source": "web",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": None,
                    "decision_rule": "web_no_value",
                    "evidence_json": "{}",
                    "category_key": "concealer",
                },
                {
                    "timestamp": "2026-02-09T01:00:00Z",
                    "source": "vision",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "vision_confident",
                    "evidence_json": "{}",
                    "category_key": "concealer",
                },
            ]

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            raise AssertionError(
                "Stage fallback should not run when explicit audit exists."
            )

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)
    monkeypatch.setattr(
        api_mod, "_load_resolution_consensus_frame", lambda: api_mod.pl.DataFrame()
    )

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": None,
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "web"
    assert attached["decision_rule"] == "web_no_value"
    assert attached["value"] is None


def test_attach_attribute_audit_uses_history_counts_without_consensus(
    monkeypatch,
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return [
                {
                    "timestamp": "2026-02-10T10:00:00Z",
                    "source": "llm",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "llm_choice",
                    "evidence_json": '{"confidence": 0.9}',
                    "category_key": "concealer",
                },
                {
                    "timestamp": "2026-02-09T10:00:00Z",
                    "source": "llm",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "llm_choice",
                    "evidence_json": '{"confidence": 0.9}',
                    "category_key": "concealer",
                },
                {
                    "timestamp": "2026-02-08T10:00:00Z",
                    "source": "llm",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "llm_choice",
                    "evidence_json": '{"confidence": 0.9}',
                    "category_key": "concealer",
                },
                {
                    "timestamp": "2026-02-07T10:00:00Z",
                    "source": "deterministic",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "deterministic_text_match",
                    "evidence_json": "{}",
                    "category_key": "concealer",
                },
            ]

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            raise AssertionError(
                "Stage fallback should not run when explicit audit exists."
            )

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)
    monkeypatch.setattr(
        api_mod, "_load_resolution_consensus_frame", lambda: api_mod.pl.DataFrame()
    )

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": "natural",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "llm"
    assert attached["value"] == "natural"
    assert attached["support_runs"] == 3
    assert attached["total_runs"] == 3
    assert attached["agreement_rate"] == 1.0
    assert attached["certainty_class"] == "sure"


def test_attach_history_metrics_counts_deterministic_once() -> None:
    payload = {
        "value": "warm",
        "source": None,
    }
    rows = [
        {
            "timestamp": "2026-02-10T10:00:00Z",
            "source": "deterministic",
            "value": "warm",
        },
        {
            "timestamp": "2026-02-09T10:00:00Z",
            "source": "deterministic",
            "value": "warm",
        },
        {
            "timestamp": "2026-02-08T10:00:00Z",
            "source": "deterministic",
            "value": "warm",
        },
        {
            "timestamp": "2026-02-07T10:00:00Z",
            "source": "llm",
            "value": "warm",
        },
        {
            "timestamp": "2026-02-06T10:00:00Z",
            "source": "web",
            "value": "cool",
        },
    ]

    attached = api_mod._attach_history_metrics_from_audit_rows(payload, rows)

    assert attached is True
    assert payload["support_runs"] == 2
    assert payload["total_runs"] == 3
    assert payload["agreement_rate"] == 2.0 / 3.0


def test_attach_attribute_audit_appends_consensus_promotion_fields(
    monkeypatch,
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return [
                {
                    "timestamp": "2026-02-09T01:00:00Z",
                    "source": "llm",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "decision_rule": "llm_choice",
                    "evidence_json": '{"confidence": 0.9}',
                    "category_key": "concealer",
                }
            ]

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            raise AssertionError(
                "Stage fallback should not run when explicit audit exists."
            )

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)
    consensus_df = api_mod.pl.DataFrame(
        [
            {
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "concealer",
                "attribute_id": "finish",
                "consensus_value": "natural",
                "support_runs": 3,
                "total_runs": 4,
                "agreement_rate": 0.75,
                "step_count": 2,
                "supporting_steps": ["deterministic", "llm_pdp_lookup"],
                "certainty_class": "sure",
                "max_confidence": 0.95,
                "last_seen_at": "2026-02-09T01:00:00Z",
                "last_recorded_at": "2026-02-09T01:00:00Z",
            }
        ]
    )
    monkeypatch.setattr(
        api_mod, "_load_resolution_consensus_frame", lambda: consensus_df
    )

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": "natural",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["promoted"] is True
    assert attached["support_runs"] == 3
    assert attached["total_runs"] == 4
    assert attached["agreement_rate"] == 0.75
    assert attached["certainty_class"] == "sure"
    assert attached["supporting_steps"] == ["deterministic", "llm_pdp_lookup"]


def test_attach_attribute_audit_falls_back_to_stage_rows_and_matches_value(
    monkeypatch,
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return []

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            assert sources == ("llm", "deterministic")
            return [
                {
                    "source": "llm",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "oov_candidate": "dewy natural",
                    "note": "PDP mentions dewy natural finish.",
                    "updated_at": "2026-02-09T01:00:00Z",
                },
                {
                    "source": "deterministic",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "matte",
                    "updated_at": "2026-02-09T00:00:00Z",
                },
            ]

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": "matte",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "deterministic"
    assert attached["decision_rule"] == "deterministic_stage_value"
    assert attached["evidence"]["stage_source"] == "deterministic"
    assert attached["promoted"] is False
    assert attached["support_runs"] == 1
    assert attached["total_runs"] == 1
    assert attached["agreement_rate"] == 1.0
    assert attached["certainty_class"] == "uncertain"
    assert attached["supporting_steps"] == ["deterministic"]


def test_attach_attribute_audit_stage_fallback_includes_llm_note_and_oov(
    monkeypatch,
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return []

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            assert sources == ("llm", "deterministic")
            return [
                {
                    "source": "llm",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "natural",
                    "oov_candidate": "dewy natural",
                    "note": "PDP copy says dewy-natural finish.",
                    "updated_at": "2026-02-09T01:00:00Z",
                }
            ]

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": "natural",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "llm"
    assert attached["decision_rule"] == "llm_stage_value"
    assert attached["evidence"]["oov_candidate"] == "dewy natural"
    assert attached["evidence"]["note"] == "PDP copy says dewy-natural finish."
    assert attached["promoted"] is False
    assert attached["support_runs"] == 1
    assert attached["total_runs"] == 1
    assert attached["agreement_rate"] == 1.0
    assert attached["certainty_class"] == "uncertain"
    assert attached["supporting_steps"] == ["llm_pdp_lookup"]


def test_attach_attribute_audit_stage_fallback_matches_attribute_id_alias(
    monkeypatch,
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return []

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            assert sources == ("llm", "deterministic")
            if attribute_id != "application area":
                return []
            return [
                {
                    "source": "deterministic",
                    "row_type": "parent",
                    "retailer": "sephora",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "application area",
                    "value": "face",
                    "updated_at": "2026-02-09T01:00:00Z",
                }
            ]

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "application area": "face",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="application_area",
        attribute_column="application area",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "deterministic"
    assert attached["decision_rule"] == "deterministic_stage_value"
    assert attached["value"] == "face"


def test_attach_attribute_audit_falls_back_to_resolution_ledger(monkeypatch) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            return []

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert keys == [("sephora", "P1", "")]
            assert sources == ("llm", "deterministic")
            return []

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)

    ledger_df = api_mod.pl.DataFrame(
        [
            {
                "run_id": "run-1",
                "recorded_at": "2026-02-09T05:00:00Z",
                "step": "brand_web_search",
                "source": "web",
                "decision_rule": "web_confident",
                "row_type": "parent",
                "retailer": "sephora",
                "parent_product_id": "P1",
                "variant_id": "",
                "canonical_id": "canon-1",
                "category_key": "concealer",
                "attribute_id": "finish",
                "value": "natural",
                "confidence": 0.95,
                "evidence_url": "https://brand.example/p1",
            }
        ]
    )
    monkeypatch.setattr(
        api_mod.attribute_resolution_history,
        "read_resolution_ledger",
        lambda: ledger_df,
    )

    records = [
        {
            "retailer": "sephora",
            "parent_product_id": "P1",
            "finish": "natural",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="finish",
        attribute_column="finish",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "web"
    assert attached["decision_rule"] == "web_confident"
    assert attached["evidence"]["provenance"] == "resolution_ledger"
    assert attached["evidence"]["confidence"] == 0.95
    assert attached["evidence"]["evidence_url"] == "https://brand.example/p1"


def test_attach_attribute_audit_falls_back_to_web_fill_audit_csv(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "base"
            assert row_type == "parent"
            assert keys == [("ulta", "P1", "")]
            return []

        def fetch_attribute_stage_rows(self, *, attribute_id, row_type, keys, sources):
            assert attribute_id == "base"
            assert row_type == "parent"
            assert keys == [("ulta", "P1", "")]
            assert sources == ("llm", "deterministic")
            return []

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)
    monkeypatch.setattr(
        api_mod.attribute_resolution_history,
        "read_resolution_ledger",
        lambda: api_mod.pl.DataFrame(),
    )

    web_csv = tmp_path / "attribute_web_fill_audit.csv"
    api_mod.pl.DataFrame(
        [
            {
                "category_key": "eyeliner",
                "source_retailer": "ulta",
                "source_parent_product_id": "P1",
                "requested_parent_attributes": "base, finish",
                "requested_variant_attributes": "{}",
                "filled_parent_attributes": '{"base":{"value":"silicone-based","confidence":0.9,"evidence_url":"https://brand.example/p1"}}',
                "filled_variant_attributes": "{}",
            }
        ]
    ).write_csv(web_csv)
    monkeypatch.setattr(api_mod, "_WEB_FILL_AUDIT_CSV", web_csv)
    monkeypatch.setattr(api_mod, "_VISION_FILL_AUDIT_CSV", tmp_path / "missing.csv")

    records = [
        {
            "retailer": "ulta",
            "parent_product_id": "P1",
            "base": "silicone-based",
        }
    ]
    api_mod._attach_attribute_audit(
        records,
        record_type="parent",
        attribute_id="base",
        attribute_column="base",
    )

    attached = records[0].get("attribute_audit")
    assert attached is not None
    assert attached["source"] == "web"
    assert attached["decision_rule"] == "web_confident"
    assert attached["value"] == "silicone-based"
    assert attached["evidence"]["provenance"] == "web_fill_audit_csv"
    assert attached["evidence"]["evidence_url"] == "https://brand.example/p1"


def test_attach_coverage_confidence_metrics_aggregates_per_attribute(
    monkeypatch,
) -> None:
    class UnexpectedStore:
        def __init__(self, _path) -> None:
            raise AssertionError("local PDP database fallback should not be used with consensus.")

    frame = api_mod.pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "finish": "matte",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "P2",
                "finish": "dewy",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "P3",
                "finish": "n/a",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "P4",
                "finish": "not in taxonomy (shade)",
            },
        ]
    )
    consensus_df = api_mod.pl.DataFrame(
        [
            {
                "row_type": "parent",
                "retailer": "ulta",
                "parent_product_id": "P1",
                "variant_id": "",
                "attribute_id": "finish",
                "support_runs": 3,
                "total_runs": 4,
                "agreement_rate": 0.75,
                "certainty_class": "uncertain",
                "supporting_steps": ["deterministic"],
            },
            {
                "row_type": "parent",
                "retailer": "ulta",
                "parent_product_id": "P2",
                "variant_id": "",
                "attribute_id": "finish",
                "support_runs": 2,
                "total_runs": 2,
                "agreement_rate": 1.0,
                "certainty_class": "sure",
                "supporting_steps": ["deterministic"],
            },
        ]
    )
    monkeypatch.setattr(
        api_mod, "_load_resolution_consensus_frame", lambda: consensus_df
    )
    monkeypatch.setattr(api_mod, "PDPStore", UnexpectedStore)

    report = {
        "attributes": [
            {
                "id": "finish",
                "label": "Finish",
                "column": "finish",
                "total": 4,
                "filled": 2,
            }
        ]
    }
    api_mod._attach_coverage_confidence_metrics(
        report,
        frame=frame,
        record_type="parent",
        placeholder_values=["n/a", "unknown", "not in taxonomy"],
    )

    confidence = report["attributes"][0]
    assert confidence["confidence_support_avg"] == 2.5
    assert confidence["confidence_total_avg"] == 3.0
    assert confidence["confidence_pct"] == 5.0 / 6.0
    assert confidence["confidence_samples"] == 2


def test_attach_coverage_confidence_metrics_falls_back_to_audit_history(
    monkeypatch,
) -> None:
    class FakeStore:
        def __init__(self, _path) -> None:
            pass

        def fetch_attribute_audit_rows(self, *, attribute_id, row_type, keys):
            assert attribute_id == "finish"
            assert row_type == "parent"
            assert set(keys) == {("ulta", "P1", ""), ("ulta", "P2", "")}
            return [
                {
                    "timestamp": "2026-02-10T00:00:00Z",
                    "source": "deterministic",
                    "retailer": "ulta",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "warm",
                    "decision_rule": "deterministic_text_match",
                },
                {
                    "timestamp": "2026-02-09T00:00:00Z",
                    "source": "llm",
                    "retailer": "ulta",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "warm",
                    "decision_rule": "llm_choice",
                },
                {
                    "timestamp": "2026-02-08T00:00:00Z",
                    "source": "web",
                    "retailer": "ulta",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "warm",
                    "decision_rule": "web_confident",
                },
                {
                    "timestamp": "2026-02-07T00:00:00Z",
                    "source": "vision",
                    "retailer": "ulta",
                    "parent_product_id": "P1",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "warm",
                    "decision_rule": "vision_confident",
                },
                {
                    "timestamp": "2026-02-10T00:00:00Z",
                    "source": "deterministic",
                    "retailer": "ulta",
                    "parent_product_id": "P2",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "cool",
                    "decision_rule": "deterministic_text_match",
                },
                {
                    "timestamp": "2026-02-09T00:00:00Z",
                    "source": "llm",
                    "retailer": "ulta",
                    "parent_product_id": "P2",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "cool",
                    "decision_rule": "llm_choice",
                },
                {
                    "timestamp": "2026-02-08T00:00:00Z",
                    "source": "web",
                    "retailer": "ulta",
                    "parent_product_id": "P2",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "warm",
                    "decision_rule": "web_confident",
                },
                {
                    "timestamp": "2026-02-07T00:00:00Z",
                    "source": "vision",
                    "retailer": "ulta",
                    "parent_product_id": "P2",
                    "variant_id": "",
                    "attribute_id": "finish",
                    "value": "warm",
                    "decision_rule": "vision_confident",
                },
            ]

    monkeypatch.setattr(api_mod, "PDPStore", FakeStore)
    monkeypatch.setattr(
        api_mod, "_load_resolution_consensus_frame", lambda: api_mod.pl.DataFrame()
    )

    frame = api_mod.pl.DataFrame(
        [
            {
                "retailer": "ulta",
                "parent_product_id": "P1",
                "finish": "warm",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "P2",
                "finish": "cool",
            },
            {
                "retailer": "ulta",
                "parent_product_id": "P3",
                "finish": "n/a",
            },
        ]
    )
    report = {
        "attributes": [
            {
                "id": "finish",
                "label": "Finish",
                "column": "finish",
                "total": 3,
                "filled": 2,
            }
        ]
    }

    api_mod._attach_coverage_confidence_metrics(
        report,
        frame=frame,
        record_type="parent",
        placeholder_values=["n/a", "unknown", "not in taxonomy"],
    )

    confidence = report["attributes"][0]
    assert confidence["confidence_support_avg"] == 3.0
    assert confidence["confidence_total_avg"] == 4.0
    assert confidence["confidence_pct"] == 0.75
    assert confidence["confidence_samples"] == 2
