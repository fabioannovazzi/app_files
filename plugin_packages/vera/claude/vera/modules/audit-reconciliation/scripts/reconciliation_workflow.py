"""Generic workflow orchestration for Claude audit reconciliation.

This module is intentionally a library helper, not a CLI. Case-specific Claude
workpapers can import it after they have normalized source documents into open
items and evidence rows.
"""

from __future__ import annotations

import sys as _bootstrap_sys

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__audit_reconciliation_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/audit-reconciliation"
)

import os as _bootstrap_os

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_audit_reconciliation_implementation_bootstrap",
}
_bootstrap_stat = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _bootstrap_stat.st_mode & 0o170000 != 0o100000 or _bootstrap_stat.st_nlink != 1:
    raise RuntimeError(
        "implementation bootstrap must be an ordinary single-link regular file"
    )
_bootstrap_descriptor = _bootstrap_os.open(
    _BOOTSTRAP_PATH,
    _bootstrap_os.O_RDONLY | getattr(_bootstrap_os, "O_NOFOLLOW", 0),
)
try:
    _bootstrap_open_stat = _bootstrap_os.fstat(_bootstrap_descriptor)
    _bootstrap_identity = (
        _bootstrap_stat.st_dev,
        _bootstrap_stat.st_ino,
        _bootstrap_stat.st_size,
        _bootstrap_stat.st_mtime_ns,
        _bootstrap_stat.st_nlink,
    )
    if _bootstrap_identity != (
        _bootstrap_open_stat.st_dev,
        _bootstrap_open_stat.st_ino,
        _bootstrap_open_stat.st_size,
        _bootstrap_open_stat.st_mtime_ns,
        _bootstrap_open_stat.st_nlink,
    ):
        raise RuntimeError("implementation bootstrap changed before it was read")
    with _bootstrap_os.fdopen(
        _bootstrap_descriptor,
        "rb",
        closefd=False,
    ) as _bootstrap_handle:
        _bootstrap_source = _bootstrap_handle.read()
    _bootstrap_after_stat = _bootstrap_os.fstat(_bootstrap_descriptor)
    if (
        _bootstrap_identity
        != (
            _bootstrap_after_stat.st_dev,
            _bootstrap_after_stat.st_ino,
            _bootstrap_after_stat.st_size,
            _bootstrap_after_stat.st_mtime_ns,
            _bootstrap_after_stat.st_nlink,
        )
        or len(_bootstrap_source) != _bootstrap_after_stat.st_size
    ):
        raise RuntimeError("implementation bootstrap changed while it was read")
finally:
    _bootstrap_os.close(_bootstrap_descriptor)
# Execute only the pre-opened single-link bootstrap source.
exec(  # nosec B102
    compile(_bootstrap_source, _BOOTSTRAP_PATH, "exec"),
    _BOOTSTRAP_NAMESPACE,
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"](
    (
        "locale_support",
        "reconciliation_helpers",
        "accountant_report",
        "review_session",
        "workpaper_outputs",
    )
)
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import re
import sys
import zipfile
from collections.abc import Mapping
from functools import wraps
from pathlib import Path
from typing import Any

try:
    from .accountant_report import write_accountant_report_workbook
    from .audit_assurance import (
        finalize_assurance_run,
        prepare_assurance_run,
        rollback_assurance_run,
    )
    from .locale_support import language_pack, normalize_language
    from .reconciliation_helpers import (
        bank_allocation_candidates,
        build_codex_review_packet,
        checks_pass,
        closed_bank_allocation_controls,
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

    from accountant_report import write_accountant_report_workbook  # type: ignore
    from audit_assurance import (  # type: ignore
        finalize_assurance_run,
        prepare_assurance_run,
        rollback_assurance_run,
    )
    from locale_support import language_pack, normalize_language  # type: ignore
    from reconciliation_helpers import (  # type: ignore
        bank_allocation_candidates,
        build_codex_review_packet,
        checks_pass,
        closed_bank_allocation_controls,
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
    from review_session import (  # type: ignore
        write_review_session_artifacts,
        write_run_intake,
    )
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


def source_qualification_checks(
    qualifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert mechanically validated source statuses into a completion gate."""

    if not qualifications:
        return []
    blocked = [
        str(row.get("qualification_id") or "")
        for row in qualifications
        if row.get("status") != "qualified"
    ]
    return [
        {
            "check": "source_layouts_qualified",
            "status": "PASS" if not blocked else "FAIL",
            "actual": len(qualifications) - len(blocked),
            "expected": len(qualifications),
            "note": "; ".join(blocked[:10]),
        }
    ]


def _stabilize_office_package(path: Path) -> None:
    """Make generated OOXML bytes replayable for audit receipt comparison.

    Fixed core-property values, member order, and ZIP timestamps are mechanical
    package metadata. Normalizing them removes run-clock noise without changing
    workbook or document content.
    """

    with zipfile.ZipFile(path) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    stable_entries: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info, data in entries:
        if info.filename == "docProps/core.xml":
            for tag in (b"created", b"modified"):
                pattern = (
                    rb"(<dcterms:" + tag + rb"\b[^>]*>)[^<]*(</dcterms:" + tag + rb">)"
                )
                data = re.sub(
                    pattern,
                    rb"\g<1>2000-01-01T00:00:00Z\g<2>",
                    data,
                )
        stable_info = zipfile.ZipInfo(
            filename=info.filename,
            date_time=(1980, 1, 1, 0, 0, 0),
        )
        stable_info.compress_type = info.compress_type
        stable_info.comment = info.comment
        stable_info.internal_attr = info.internal_attr
        stable_info.external_attr = info.external_attr
        stable_info.create_system = info.create_system
        stable_entries.append((stable_info, data))
    temporary = path.with_name(f".{path.name}.stable")
    with zipfile.ZipFile(
        temporary,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for info, data in sorted(stable_entries, key=lambda item: item[0].filename):
            archive.writestr(info, data)
    temporary.replace(path)


def _rollback_on_workflow_failure(function: Any) -> Any:
    """Restore the pre-run output image after any downstream workflow failure."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        completed = False
        try:
            result = function(*args, **kwargs)
            completed = True
            return result
        finally:
            if not completed and "output_dir" in kwargs:
                rollback_assurance_run(Path(kwargs["output_dir"]))

    return wrapped


@_rollback_on_workflow_failure
def build_reconciliation_artifacts(
    *,
    output_dir: str | Path,
    open_items: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    assumptions: dict[str, Any],
    source_inventory: list[dict[str, Any]] | None = None,
    source_qualifications: list[dict[str, Any]] | None = None,
    source_artifact_root: str | Path | None = None,
    source_artifact_receipts: list[dict[str, Any]] | None = None,
    reviewed_source_decision_receipts: list[dict[str, Any]] | None = None,
    extraction_errors: list[dict[str, Any]] | None = None,
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
    client_engagement: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    title: str | None = None,
    narrative: str = "",
    next_steps: list[str] | None = None,
    language: str = "it",
    excel_name: str = "riconciliazione_audit.xlsx",
    word_name: str = "relazione_riconciliazione_audit.docx",
    fail_on_check_errors: bool = True,
    defer_assurance_finalization: bool = False,
    expected_predecessor_checkpoint: str | None = None,
) -> dict[str, Any]:
    """Run deterministic reconciliation and write standard Excel/Word outputs.

    Inputs must already be normalized. This function does not parse PDFs or make
    LLM decisions; it coordinates deterministic helpers and output generation.
    """

    out_dir = Path(output_dir)
    assurance_context = prepare_assurance_run(
        output_dir=out_dir,
        open_items=open_items,
        evidence_rows=evidence_rows,
        assumptions=assumptions,
        source_root=(
            Path(source_artifact_root) if source_artifact_root is not None else None
        ),
        source_receipts=source_artifact_receipts or [],
        reviewed_source_decisions=reviewed_source_decision_receipts or [],
        source_qualifications=source_qualifications or [],
        client_engagement=client_engagement,
        expected_predecessor_checkpoint=expected_predecessor_checkpoint,
    )
    review_authority = assurance_context.get("professional_review_authority")
    successor_run_id = (
        str(review_authority.get("run_id"))
        if isinstance(review_authority, dict)
        and review_authority.get("origin") == "applied_decisions"
        and isinstance(review_authority.get("run_id"), str)
        and review_authority.get("run_id")
        else None
    )
    normalized_client_engagement = assurance_context.get("client_engagement")
    if (
        isinstance(normalized_client_engagement, dict)
        and successor_run_id is not None
        and successor_run_id != normalized_client_engagement.get("run_id")
    ):
        raise ValueError(
            "Successor review run ID does not match the client engagement run."
        )
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
        client_engagement=normalized_client_engagement,
        run_id=successor_run_id or run_id,
    )

    reconciliation_rows = reconcile_open_items(open_items, evidence_rows, assumptions)
    relationship_allocation_ledgers, _ = closed_bank_allocation_controls(
        reconciliation_rows,
        evidence_rows,
        assumptions,
    )
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
            priority_rows=review_signals,
        )
    )
    checks = [
        *source_qualification_checks(source_qualifications or []),
        *reconciliation_checks(open_items, reconciliation_rows),
        *codex_review_checks(
            reconciliation_rows,
            review,
            require_completed_review=require_completed_review,
            high_value_count=review_high_value_count,
            random_count=review_random_count,
            challenged_rows=challenged_rows,
            priority_rows=review_signals,
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
        extraction_errors=extraction_errors,
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
    for office_path in (excel_path, accountant_report_path, word_path):
        _stabilize_office_package(Path(office_path))

    source_processing = {
        "extraction_errors": extraction_errors or [],
        "ledger_balance_rows": ledger_balance_rows or [],
        "journal_rollforward_rows": aggregate_rollforward_rows or [],
        "journal_rollforward_summary": aggregate_rollforward_summary or [],
    }
    analyses = {
        "aging_summary": aging_summary,
        "bank_allocation_candidates": bank_candidates,
        "cutoff_window_movements": cutoff_movements,
        "document_source_map": source_map,
        "evidence_concentration": evidence_concentration,
        "external_evidence_detail": external_detail,
        "external_evidence_summary": external_summary,
        "post_cutoff_candidates": post_cutoff_candidates,
        "reversal_candidates": reversal_candidates,
        "review_signals": review_signals,
    }
    result = {
        "excel_path": str(excel_path),
        "accountant_report_path": str(accountant_report_path),
        "word_path": str(word_path),
        "assumptions": assumptions,
        "client_engagement": normalized_client_engagement,
        "source_qualifications": source_qualifications or [],
        "source_processing": source_processing,
        "analyses": analyses,
        "reconciliation_rows": reconciliation_rows,
        "bank_allocation_candidates": bank_candidates,
        "relationship_allocation_ledgers": relationship_allocation_ledgers,
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
        "assurance_context": assurance_context,
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
    if not defer_assurance_finalization:
        result["assurance"] = finalize_assurance_run(
            output_dir=out_dir,
            context=assurance_context,
            reconciliation_rows=reconciliation_rows,
            allocation_ledgers=relationship_allocation_ledgers,
            checks=checks,
            review_rows=review,
            source_qualifications=source_qualifications or [],
            source_processing=source_processing,
            analyses=analyses,
            declared_outputs=[
                Path(excel_path),
                Path(accountant_report_path),
                Path(word_path),
            ],
            workbook_name=Path(excel_path).name,
        )
    return result
