from __future__ import annotations

from pathlib import Path

import polars as pl

from modules.pdp.attribute_resolution_history import (
    append_resolution_ledger_rows,
    read_resolution_ledger,
    write_resolution_consensus,
)


def _base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": "run-1",
        "recorded_at": "2026-02-01T00:00:00Z",
        "step": "deterministic",
        "source": "deterministic",
        "decision_rule": "deterministic_text_match",
        "row_type": "parent",
        "retailer": "sephora",
        "parent_product_id": "P1",
        "variant_id": "",
        "canonical_id": "canon-1",
        "category_key": "lipstick",
        "attribute_id": "finish",
        "value": "matte",
        "confidence": None,
        "evidence_url": None,
    }
    row.update(overrides)
    return row


def test_append_resolution_ledger_rows_handles_late_confidence_float(
    tmp_path: Path,
) -> None:
    ledger_dir = tmp_path / "ledger"
    rows = [
        _base_row(run_id=f"run-{index}", confidence=None)
        for index in range(101)
    ]
    rows.append(
        _base_row(
            run_id="run-float",
            confidence=0.92,
        )
    )

    chunk_path = append_resolution_ledger_rows(rows, ledger_dir=ledger_dir)

    assert chunk_path is not None
    assert chunk_path.exists()
    ledger = read_resolution_ledger(ledger_dir=ledger_dir)
    assert ledger.height == 102
    float_row = ledger.filter(pl.col("run_id") == "run-float").row(0, named=True)
    assert float_row["confidence"] == 0.92


def test_resolution_history_consensus_marks_repeated_value_as_sure(
    tmp_path: Path,
) -> None:
    ledger_dir = tmp_path / "ledger"
    consensus_path = tmp_path / "consensus.parquet"

    append_resolution_ledger_rows(
        [
            _base_row(
                run_id="run-1", recorded_at="2026-02-01T00:00:00Z", step="deterministic"
            ),
            _base_row(
                run_id="run-1",
                recorded_at="2026-02-01T00:00:01Z",
                row_type="variant",
                variant_id="V1",
                attribute_id="coverage",
                value="light",
            ),
        ],
        ledger_dir=ledger_dir,
    )
    append_resolution_ledger_rows(
        [
            _base_row(
                run_id="run-2",
                recorded_at="2026-02-02T00:00:00Z",
                step="llm_pdp_lookup",
                source="llm",
                decision_rule="llm_choice",
            ),
            _base_row(
                run_id="run-2",
                recorded_at="2026-02-02T00:00:01Z",
                row_type="variant",
                variant_id="V1",
                attribute_id="coverage",
                value="medium",
                step="llm_pdp_lookup",
                source="llm",
                decision_rule="llm_choice",
            ),
        ],
        ledger_dir=ledger_dir,
    )
    append_resolution_ledger_rows(
        [
            _base_row(
                run_id="run-3",
                recorded_at="2026-02-03T00:00:00Z",
                step="brand_web_search",
                source="web",
                decision_rule="web_confident",
                confidence=0.95,
                evidence_url="https://example.com/product",
            ),
        ],
        ledger_dir=ledger_dir,
    )

    ledger = read_resolution_ledger(ledger_dir=ledger_dir)
    assert ledger.height == 5

    consensus = write_resolution_consensus(
        ledger_dir=ledger_dir,
        output_path=consensus_path,
    )
    assert consensus_path.exists()
    assert isinstance(pl.read_parquet(consensus_path), pl.DataFrame)

    parent_row = consensus.filter(
        (pl.col("row_type") == "parent")
        & (pl.col("attribute_id") == "finish")
        & (pl.col("parent_product_id") == "P1")
    ).row(0, named=True)
    assert parent_row["consensus_value"] == "matte"
    assert parent_row["support_runs"] == 3
    assert parent_row["total_runs"] == 3
    assert parent_row["agreement_rate"] == 1.0
    assert parent_row["certainty_class"] == "sure"
    assert set(parent_row["supporting_steps"]) == {
        "brand_web_search",
        "deterministic",
        "llm_pdp_lookup",
    }

    variant_row = consensus.filter(
        (pl.col("row_type") == "variant")
        & (pl.col("attribute_id") == "coverage")
        & (pl.col("variant_id") == "V1")
    ).row(0, named=True)
    assert variant_row["support_runs"] == 1
    assert variant_row["total_runs"] == 2
    assert variant_row["agreement_rate"] == 0.5
    assert variant_row["certainty_class"] == "uncertain"


def test_resolution_history_consensus_ignores_placeholder_values(
    tmp_path: Path,
) -> None:
    ledger_dir = tmp_path / "ledger"
    consensus_path = tmp_path / "consensus.parquet"

    append_resolution_ledger_rows(
        [
            _base_row(run_id="run-1", value="N/A"),
            _base_row(run_id="run-2", value="not in taxonomy"),
            _base_row(run_id="run-3", value=""),
        ],
        ledger_dir=ledger_dir,
    )

    consensus = write_resolution_consensus(
        ledger_dir=ledger_dir,
        output_path=consensus_path,
    )
    assert consensus.is_empty()


def test_resolution_history_consensus_requires_three_runs_for_sure(
    tmp_path: Path,
) -> None:
    ledger_dir = tmp_path / "ledger"
    consensus_path = tmp_path / "consensus.parquet"

    append_resolution_ledger_rows(
        [
            _base_row(run_id="run-1", step="deterministic"),
            _base_row(run_id="run-2", step="deterministic"),
        ],
        ledger_dir=ledger_dir,
    )

    consensus = write_resolution_consensus(
        ledger_dir=ledger_dir,
        output_path=consensus_path,
    )

    row = consensus.filter(
        (pl.col("row_type") == "parent")
        & (pl.col("attribute_id") == "finish")
        & (pl.col("parent_product_id") == "P1")
    ).row(0, named=True)
    assert row["support_runs"] == 2
    assert row["total_runs"] == 2
    assert row["agreement_rate"] == 1.0
    assert row["certainty_class"] == "uncertain"


def test_resolution_history_consensus_uses_recent_four_run_majority(
    tmp_path: Path,
) -> None:
    ledger_dir = tmp_path / "ledger"
    consensus_path = tmp_path / "consensus.parquet"

    append_resolution_ledger_rows(
        [
            _base_row(run_id="run-1", recorded_at="2026-02-01T00:00:00Z", value="A"),
            _base_row(run_id="run-2", recorded_at="2026-02-02T00:00:00Z", value="A"),
            _base_row(run_id="run-3", recorded_at="2026-02-03T00:00:00Z", value="B"),
            _base_row(run_id="run-4", recorded_at="2026-02-04T00:00:00Z", value="A"),
        ],
        ledger_dir=ledger_dir,
    )

    consensus = write_resolution_consensus(
        ledger_dir=ledger_dir,
        output_path=consensus_path,
    )

    row = consensus.filter(
        (pl.col("row_type") == "parent")
        & (pl.col("attribute_id") == "finish")
        & (pl.col("parent_product_id") == "P1")
    ).row(0, named=True)
    assert row["consensus_value"] == "A"
    assert row["support_runs"] == 3
    assert row["total_runs"] == 4
    assert row["agreement_rate"] == 0.75
    assert row["certainty_class"] == "sure"


def test_resolution_history_consensus_includes_recovery_runs_by_default(
    tmp_path: Path,
) -> None:
    ledger_dir = tmp_path / "ledger"
    consensus_path = tmp_path / "consensus.parquet"

    append_resolution_ledger_rows(
        [
            _base_row(run_id="run-1", recorded_at="2026-02-01T00:00:00Z", value="A"),
            _base_row(run_id="run-2", recorded_at="2026-02-02T00:00:00Z", value="A"),
            _base_row(run_id="run-3", recorded_at="2026-02-03T00:00:00Z", value="A"),
            _base_row(
                run_id="prejoin-sales-recovery-20260209T010000000000Z-abc1234567",
                recorded_at="2026-02-04T00:00:00Z",
                value="A",
            ),
        ],
        ledger_dir=ledger_dir,
    )

    consensus = write_resolution_consensus(
        ledger_dir=ledger_dir,
        output_path=consensus_path,
    )

    row = consensus.filter(
        (pl.col("row_type") == "parent")
        & (pl.col("attribute_id") == "finish")
        & (pl.col("parent_product_id") == "P1")
    ).row(0, named=True)
    assert row["consensus_value"] == "A"
    assert row["support_runs"] == 4
    assert row["total_runs"] == 4
    assert row["agreement_rate"] == 1.0
    assert row["certainty_class"] == "sure"


def test_resolution_history_consensus_excludes_selected_run_ids_from_counts(
    tmp_path: Path,
) -> None:
    ledger_dir = tmp_path / "ledger"
    consensus_path = tmp_path / "consensus.parquet"
    excluded_run_id = "prejoin-sales-20260209T103729673823Z-cb26248c4a"

    append_resolution_ledger_rows(
        [
            _base_row(run_id="run-1", recorded_at="2026-02-01T00:00:00Z", value="A"),
            _base_row(run_id="run-2", recorded_at="2026-02-02T00:00:00Z", value="A"),
            _base_row(run_id=excluded_run_id, recorded_at="2026-02-03T00:00:00Z", value="A"),
        ],
        ledger_dir=ledger_dir,
    )

    consensus = write_resolution_consensus(
        ledger_dir=ledger_dir,
        output_path=consensus_path,
        excluded_run_ids=[excluded_run_id],
    )

    row = consensus.filter(
        (pl.col("row_type") == "parent")
        & (pl.col("attribute_id") == "finish")
        & (pl.col("parent_product_id") == "P1")
    ).row(0, named=True)
    assert row["consensus_value"] == "A"
    assert row["support_runs"] == 2
    assert row["total_runs"] == 2
    assert row["agreement_rate"] == 1.0
    assert row["certainty_class"] == "uncertain"
