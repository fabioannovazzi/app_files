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

INVARIANT_TESTS = (
    "test_nonzero_account_cannot_be_excluded_from_statement_generation",
    "test_validation_defensively_blocks_tampered_nonzero_exclusions",
    "test_mapping_patch_preserves_unsubmitted_professional_decisions",
    "test_oic_pack_selection_changes_required_professional_review_questions",
    "test_failed_xbrl_review_job_leaves_no_partial_output_and_can_retry",
    "test_failed_export_leaves_no_partial_output_and_can_retry",
    "test_xbrl_review_rejects_symbolic_link_in_output_ancestor",
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
    test_file = repository / "tests/plugins/test_bilancio_xbrl_it_plugin.py"
    privacy_validator = (
        repository
        / "plugins/vera/skills/privacy-surface-review/scripts/validate_privacy_surfaces.py"
    )
    if not test_file.is_file() or not privacy_validator.is_file():
        raise SystemExit(
            "Mandatory review probes must run from the app_files source repository"
        )
    nodes = [f"{test_file}::{name}" for name in INVARIANT_TESTS]
    LOGGER.info("Running %d Bilancio invariant probes", len(nodes))
    _run([sys.executable, "-m", "pytest", "-q", *nodes], repository)
    LOGGER.info("Checking Vera privacy-surface fingerprint freshness")
    _run([sys.executable, str(privacy_validator)], repository)
    LOGGER.info("All Bilancio review invariants passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
