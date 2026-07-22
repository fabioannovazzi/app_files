"""Generic workflow orchestration for Codex audit reconciliation.

This module is intentionally a library helper, not a CLI. Case-specific Codex
workpapers can import it after they have normalized source documents into open
items and evidence rows.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    from .accountant_report import write_accountant_report_workbook
    from .locale_support import language_pack, normalize_language
    from .reconciliation_helpers import (
        bank_allocation_candidates,
        build_codex_review_packet,
        checks_pass,
        codex_review_checks,
        cutoff_window_movements,
        document_source_map,
        evidence_concentration_summary,
        external_evidence_detail_rows,
        external_evidence_summary,
        open_item_aging_summary,
        post_cutoff_evidence_candidates,
        reconcile_open_items,
        reconciliation_checks,
        reversal_or_compensation_candidates,
        review_signal_rows,
    )
    from .review_session import write_review_session_artifacts, write_run_intake
    from .workpaper_outputs import (
        build_audit_workbook_sheets,
        summary_from_reconciliation,
        write_excel_workpaper,
        write_word_report,
    )
except ImportError:  # pragma: no cover - supports direct import from scripts/
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import importlib.util

    from accountant_report import write_accountant_report_workbook  # type: ignore
    from locale_support import language_pack, normalize_language  # type: ignore
    from reconciliation_helpers import (  # type: ignore
        bank_allocation_candidates,
        build_codex_review_packet,
        checks_pass,
        codex_review_checks,
        cutoff_window_movements,
        document_source_map,
        evidence_concentration_summary,
        external_evidence_detail_rows,
        external_evidence_summary,
        open_item_aging_summary,
        post_cutoff_evidence_candidates,
        reconcile_open_items,
        reconciliation_checks,
        reversal_or_compensation_candidates,
        review_signal_rows,
    )

    _review_session_path = Path(__file__).resolve().parent / "review_session.py"
    _review_session_spec = importlib.util.spec_from_file_location(
        "mparanza_audit_reconciliation_review_session",
        _review_session_path,
    )
    assert _review_session_spec and _review_session_spec.loader
    _review_session = importlib.util.module_from_spec(_review_session_spec)
    sys.modules[_review_session_spec.name] = _review_session
    _review_session_spec.loader.exec_module(_review_session)
    write_review_session_artifacts = _review_session.write_review_session_artifacts
    write_run_intake = _review_session.write_run_intake
    from workpaper_outputs import (  # type: ignore
        build_audit_workbook_sheets,
        summary_from_reconciliation,
        write_excel_workpaper,
        write_word_report,
    )


DEFAULT_REPORT_TITLES = {
    "de": "Bericht zur Kontenabstimmung",
    "en": "Accounting reconciliation report",
    "es": "Informe de conciliación contable",
    "fr": "Rapport de rapprochement comptable",
    "it": "Relazione di riconciliazione contabile",
}


def default_report_title(language: str = "it") -> str:
    """Return the localized default title for the reconciliation report."""

    return DEFAULT_REPORT_TITLES[normalize_language(language)]


def default_next_steps(
    reconciliation_rows: list[dict[str, Any]], language: str = "it"
) -> list[str]:
    probable_payment = sum(
        1
        for row in reconciliation_rows
        if row.get("reconciliation_status") == "probable_payment"
    )
    unresolved = sum(
        1
        for row in reconciliation_rows
        if row.get("reconciliation_status") == "unresolved"
    )
    needs_evidence = sum(
        1
        for row in reconciliation_rows
        if row.get("reconciliation_status") == "needs_evidence"
    )
    messages = language_pack(language)["next_steps"]
    steps = []
    if probable_payment:
        steps.append(messages.get("probable_payment", messages["needs_evidence"]))
    if needs_evidence:
        steps.append(messages["needs_evidence"])
    if unresolved:
        steps.append(messages["unresolved"])
    return steps or [messages["complete"]]


def build_reconciliation_artifacts(
    *,
    output_dir: str | Path,
    open_items: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any],
    source_inventory: list[dict[str, Any]] | None = None,
    normalized_records: list[dict[str, Any]] | None = None,
    ledger_balance_rows: list[dict[str, Any]] | None = None,
    account_rollforward_check: list[dict[str, Any]] | None = None,
    aggregate_rollforward_rows: list[dict[str, Any]] | None = None,
    aggregate_rollforward_summary: list[dict[str, Any]] | None = None,
    review_rows: list[dict[str, Any]] | None = None,
    challenged_rows: list[str] | tuple[str, ...] | set[str] | None = None,
    review_seed: str = "audit-reconciliation-review",
    review_high_value_count: int = 10,
    review_random_count: int = 20,
    require_completed_review: bool = False,
    metadata: dict[str, Any] | None = None,
    title: str | None = None,
    narrative: str = "",
    next_steps: list[str] | None = None,
    language: str = "it",
    excel_name: str = "riconciliazione_audit.xlsx",
    word_name: str = "relazione_riconciliazione_audit.docx",
    fail_on_check_errors: bool = True,
) -> dict[str, Any]:
    """Run deterministic reconciliation and write standard Excel/Word outputs.

    Inputs must already be normalized. This function does not parse PDFs or make
    LLM decisions; it coordinates deterministic helpers and output generation.
    """

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_intake = write_run_intake(
        out_dir,
        assumptions=assumptions,
        source_inventory=source_inventory or [],
        language=language,
        source_hint=(
            (metadata or {}).get("Input folder")
            or (source_inventory or [{}])[0].get("source_file")
            if source_inventory
            else out_dir
        ),
    )

    reconciliation_rows = reconcile_open_items(open_items, evidence_rows, assumptions)
    bank_candidates = bank_allocation_candidates(
        reconciliation_rows, evidence_rows, assumptions
    )
    external_detail = external_evidence_detail_rows(evidence_rows, assumptions)
    external_summary = external_evidence_summary(external_detail)
    post_cutoff_candidates = post_cutoff_evidence_candidates(
        open_items, evidence_rows, assumptions
    )
    aging_summary = open_item_aging_summary(reconciliation_rows, assumptions)
    review_signals = review_signal_rows(reconciliation_rows, assumptions)
    evidence_concentration = evidence_concentration_summary(reconciliation_rows)
    source_map = document_source_map(open_items, evidence_rows, reconciliation_rows)
    reversal_candidates = reversal_or_compensation_candidates(
        reconciliation_rows, evidence_rows, assumptions
    )
    cutoff_movements = cutoff_window_movements(open_items, evidence_rows, assumptions)
    review = (
        review_rows
        if review_rows is not None
        else build_codex_review_packet(
            reconciliation_rows,
            seed=review_seed,
            high_value_count=review_high_value_count,
            random_count=review_random_count,
            challenged_rows=challenged_rows,
        )
    )
    checks = [
        *reconciliation_checks(open_items, reconciliation_rows),
        *codex_review_checks(
            reconciliation_rows,
            review,
            require_completed_review=require_completed_review,
            high_value_count=review_high_value_count,
            random_count=review_random_count,
            challenged_rows=challenged_rows,
        ),
    ]
    if fail_on_check_errors and not checks_pass(checks):
        failed = [row for row in checks if row.get("status") != "PASS"]
        labels = ", ".join(str(row.get("check")) for row in failed)
        raise ValueError(f"Reconciliation checks failed: {labels}")

    normalized = (
        normalized_records
        if normalized_records is not None
        else [*open_items, *evidence_rows]
    )
    sheets = build_audit_workbook_sheets(
        assumptions=assumptions,
        source_inventory=source_inventory or [],
        normalized_records=normalized,
        reconciliation_rows=reconciliation_rows,
        bank_allocation_candidates=bank_candidates,
        external_evidence_summary=external_summary,
        external_evidence_detail=external_detail,
        ledger_balance_rows=ledger_balance_rows,
        account_rollforward_check=account_rollforward_check,
        aggregate_rollforward_rows=aggregate_rollforward_rows,
        aggregate_rollforward_summary=aggregate_rollforward_summary,
        post_cutoff_candidates=post_cutoff_candidates,
        aging_summary=aging_summary,
        review_signals=review_signals,
        evidence_concentration=evidence_concentration,
        document_source_map=source_map,
        reversal_candidates=reversal_candidates,
        cutoff_window_movements=cutoff_movements,
        checks=checks,
        review_rows=review,
        language=language,
    )

    excel_path = write_excel_workpaper(out_dir / excel_name, sheets, language=language)
    accountant_report_path = write_accountant_report_workbook(
        out_dir / "scheda_operativa_commercialista.xlsx",
        reconciliation_rows,
        bank_allocation_candidates=bank_candidates,
        normalized_records=normalized,
    )
    word_path = write_word_report(
        out_dir / word_name,
        title=title or default_report_title(language),
        metadata=metadata or {},
        summary_rows=summary_from_reconciliation(reconciliation_rows),
        assumptions=assumptions,
        next_steps=(
            next_steps
            if next_steps is not None
            else default_next_steps(reconciliation_rows, language)
        ),
        narrative=narrative,
        source_inventory=source_inventory or [],
        external_evidence_summary=external_summary,
        account_rollforward_check=account_rollforward_check or [],
        aggregate_rollforward_summary=aggregate_rollforward_summary or [],
        post_cutoff_candidates=post_cutoff_candidates,
        aging_summary=aging_summary,
        review_signals=review_signals,
        evidence_concentration=evidence_concentration,
        document_source_map=source_map,
        reversal_candidates=reversal_candidates,
        cutoff_window_movements=cutoff_movements,
        checks=checks,
        review_rows=review,
        language=language,
    )

    result = {
        "excel_path": str(excel_path),
        "accountant_report_path": str(accountant_report_path),
        "word_path": str(word_path),
        "assumptions": assumptions,
        "reconciliation_rows": reconciliation_rows,
        "bank_allocation_candidates": bank_candidates,
        "external_evidence_summary": external_summary,
        "external_evidence_detail": external_detail,
        "ledger_balance_rows": ledger_balance_rows or [],
        "account_rollforward_check": account_rollforward_check or [],
        "aggregate_rollforward_rows": aggregate_rollforward_rows or [],
        "aggregate_rollforward_summary": aggregate_rollforward_summary or [],
        "post_cutoff_candidates": post_cutoff_candidates,
        "aging_summary": aging_summary,
        "review_signals": review_signals,
        "evidence_concentration": evidence_concentration,
        "document_source_map": source_map,
        "reversal_candidates": reversal_candidates,
        "cutoff_window_movements": cutoff_movements,
        "checks": checks,
        "review_rows": review,
        "checks_pass": checks_pass(checks),
    }
    review_session = write_review_session_artifacts(
        out_dir,
        run_id=run_intake.run_id,
        run_intake_path=run_intake.path,
        result=result,
        source_inventory=source_inventory or [],
        language=language,
    )
    result["review_session"] = {
        "run_id": review_session.run_id,
        "run_intake_path": str(review_session.run_intake_path),
        "review_payload_path": str(review_session.review_payload_path),
        "ui_decisions_path": str(review_session.ui_decisions_path),
        "review_html_path": str(review_session.review_html_path),
        "final_artifacts_path": str(review_session.final_artifacts_path),
        "review_item_count": review_session.review_item_count,
    }
    return result
