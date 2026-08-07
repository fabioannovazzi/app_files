#!/usr/bin/env python3
"""Run the mandatory adversarial probes for a Bilancio implementation review."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Sequence

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)

INVARIANT_NODES = (
    "tests/plugins/test_bilancio_xbrl_it_plugin.py::test_nonzero_account_cannot_be_excluded_from_statement_generation",
    "tests/plugins/test_bilancio_xbrl_it_plugin.py::test_validation_defensively_blocks_tampered_nonzero_exclusions",
    "tests/plugins/test_bilancio_xbrl_it_plugin.py::test_mapping_patch_preserves_unsubmitted_professional_decisions",
    "tests/plugins/test_bilancio_xbrl_it_plugin.py::test_oic_pack_selection_changes_required_professional_review_questions",
    "tests/plugins/test_bilancio_xbrl_it_plugin.py::test_failed_xbrl_review_job_leaves_no_partial_output_and_can_retry",
    "tests/plugins/test_bilancio_xbrl_it_plugin.py::test_failed_export_leaves_no_partial_output_and_can_retry",
    "tests/plugins/test_bilancio_xbrl_it_plugin.py::test_xbrl_review_rejects_symbolic_link_in_output_ancestor",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_headerless_continuation_page_remains_in_review_candidate",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_mixed_readable_and_unreadable_pdf_requires_ocr_for_every_page",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_pdf_review_requires_disposition_for_every_page_without_a_table",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_pdf_candidate_hash_binds_page_and_table_coverage",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_pdf_review_rejects_balanced_nonzero_account_exclusions",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_pdf_summary_exclusion_must_reconcile_to_named_account_rows",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_managed_ocr_runtime_rejects_tampered_model",
    "tests/plugins/test_bilancio_pdf_trial_balance.py::test_managed_ocr_runtime_requires_exact_package_pins",
    "tests/plugins/test_bilancio_intelligence_contract.py::test_auto_orchestration_requires_form_determination_before_selection",
    "tests/plugins/test_bilancio_intelligence_contract.py::test_pending_pdf_guidance_rejects_a_different_canonical_action",
)


def _run(command: Sequence[str], cwd: Path) -> None:
    """Run one gate and stop at the first failed invariant."""

    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main() -> int:
    """Run accounting, retry, path, and privacy-freshness review gates."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    repository = Path(__file__).resolve().parents[3]
    privacy_validator = (
        repository
        / "plugins/vera/skills/privacy-surface-review/scripts/validate_privacy_surfaces.py"
    )
    if not privacy_validator.is_file() or any(
        not (repository / node.partition("::")[0]).is_file() for node in INVARIANT_NODES
    ):
        raise SystemExit(
            "Mandatory review probes must run from the app_files source repository"
        )
    LOGGER.info("Running %d Bilancio invariant probes", len(INVARIANT_NODES))
    _run([sys.executable, "-m", "pytest", "-q", *INVARIANT_NODES], repository)
    LOGGER.info("Checking Vera privacy-surface fingerprint freshness")
    _run([sys.executable, str(privacy_validator)], repository)
    LOGGER.info("All Bilancio review invariants passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
