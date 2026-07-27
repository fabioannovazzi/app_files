"""Mechanical assurance gates for Report Builder delivery state.

The gates separate source/preparation/reporting closure from semantic review
and external publication.  They deliberately never infer professional
approval from self-consistent files or from a completed UI decision manifest.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["build_report_assurance_state"]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def build_report_assurance_state(
    analysis: Mapping[str, Any],
    tables: Sequence[Mapping[str, Any]],
    *,
    applied_decisions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive exact workflow gates without making semantic judgments."""

    source_failures = [
        _clean_text(table.get("table_id") or table.get("source_file"))
        for table in tables
        if _clean_text(table.get("kind")) == "error"
        or bool(_clean_text(table.get("error")))
    ]
    source_status = "passed" if tables and not source_failures else "failed"
    preparation_status = "passed" if source_status == "passed" else "blocked"
    numeric_pending = [
        _clean_text(section)
        for section in analysis.get("numeric_measure_pending_sections", [])
        if _clean_text(section)
    ]
    applied = applied_decisions if isinstance(applied_decisions, Mapping) else None
    source_mapping_review = bool(
        applied and applied.get("source_mapping_review_required") is True
    )
    if applied is None:
        semantic_status = "pending"
    elif int(applied.get("blocker_count") or 0) > 0:
        semantic_status = "blocked"
    elif int(applied.get("decision_count") or 0) == int(applied.get("item_count") or 0):
        semantic_status = "passed"
    else:
        semantic_status = "pending"
    reporting_status = (
        "passed"
        if preparation_status == "passed"
        and not numeric_pending
        and not source_mapping_review
        else "blocked"
    )
    missing_sections = [
        _clean_text(section)
        for section in analysis.get("missing_sections", [])
        if _clean_text(section)
    ]
    report_ready = bool(
        applied
        and applied.get("application_status") == "final_ready"
        and semantic_status == "passed"
        and reporting_status == "passed"
        and not missing_sections
    )
    return {
        "schema_version": "report_builder.assurance_gates.v1",
        "gates": {
            "source": {
                "status": source_status,
                "basis": "current_source_receipts_and_parse_results",
                "failure_refs": source_failures,
            },
            "preparation": {
                "status": preparation_status,
                "basis": "source_tables_analysis_and_rendered_outputs_rederived",
            },
            "reconciliation": {
                "status": "not_applicable",
                "basis": "report_builder_is_not_a_reconciliation_workflow",
            },
            "semantic_review": {
                "status": semantic_status,
                "basis": "recorded_review_decisions_only",
            },
            "reporting": {
                "status": reporting_status,
                "basis": "prepared_outputs_numeric_evidence_and_mapping_state",
                "numeric_pending_sections": numeric_pending,
                "source_mapping_review_required": source_mapping_review,
            },
            "publication": {
                "status": "withheld",
                "basis": "explicit_external_release_is_outside_this_workflow",
            },
        },
        "report_ready": report_ready,
    }
