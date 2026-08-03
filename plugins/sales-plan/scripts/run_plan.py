#!/usr/bin/env python3
"""Run Vera's reviewed Actual-to-Plan sales scenario."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

for _vendor_root in (
    PLUGIN_ROOT / "vendor" / "modules",
    PLUGIN_ROOT.parent.parent / "vendor" / "modules",
    PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        if str(_vendor_root) not in sys.path:
            sys.path.insert(0, str(_vendor_root))
        break

from plan_contract_kernel import (  # noqa: E402
    PinnedDirectory,
    canonical_json_sha256,
    file_snapshot_beneath,
    pinned_directory,
)
from prepare_sales_plan_case import (  # noqa: E402
    ENGINE_VERSION,
    RECIPE_ID,
    declared_actual_sales_path,
    prepare_sales_plan_case,
    snapshot_declared_actual_sales,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
    validate_client_workflow_run,
)

__all__ = ["PlanRunError", "main", "run_plan"]

LOGGER = logging.getLogger(__name__)
RECEIPT_NAME = "plan_execution_receipt.json"
IMPLEMENTATION_FILES = (
    SCRIPTS_DIR / "prepare_sales_plan_case.py",
    SCRIPTS_DIR / "run_plan.py",
    SCRIPTS_DIR / "plan_contract_kernel.py",
)


class PlanRunError(ValueError):
    """Raised when a Plan run request is invalid."""


def _implementation_snapshots() -> list[dict[str, Any]]:
    snapshots = []
    for path in IMPLEMENTATION_FILES:
        byte_count, sha256 = file_snapshot_beneath(path, root=path.parent)
        snapshots.append(
            {
                "path": f"scripts/{path.name}",
                "byte_count": byte_count,
                "sha256": sha256,
            }
        )
    return snapshots


def _require_unchanged_file(
    path: Path,
    *,
    byte_count: int,
    sha256: str,
    label: str,
) -> None:
    current_count, current_sha256 = file_snapshot_beneath(path, root=path.parent)
    if current_count != byte_count or current_sha256 != sha256:
        raise PlanRunError(f"{label} changed during Plan execution")


def _output_receipts(
    output_boundary: PinnedDirectory,
) -> list[dict[str, Any]]:
    receipts = []
    for name in output_boundary.names():
        if name == RECEIPT_NAME:
            raise PlanRunError(f"Plan output directory contains {RECEIPT_NAME}")
        byte_count, sha256 = output_boundary.snapshot_file(name, track=True)
        receipts.append(
            {
                "artifact_ref": Path(name).stem,
                "path": name,
                "byte_count": byte_count,
                "sha256": sha256,
            }
        )
    return receipts


def run_plan(*, case_path: Path, output_dir: Path) -> dict[str, Any]:
    """Run one reviewed Plan case and write its deterministic receipt."""

    supplied_case_path = Path(case_path)
    supplied_output_dir = Path(output_dir)
    if supplied_case_path.is_symlink():
        raise PlanRunError("case path must be a regular file")
    if supplied_output_dir.is_symlink():
        raise PlanRunError("Plan output directory cannot be a symlink")
    case_path = supplied_case_path.resolve()
    output_dir = supplied_output_dir.resolve()
    if not case_path.is_file():
        raise PlanRunError("case path must be a regular file")
    if output_dir.exists() and not output_dir.is_dir():
        raise PlanRunError("Plan output path must be a directory")
    output_dir.mkdir(parents=True, exist_ok=True)

    with pinned_directory(output_dir) as output_boundary:
        if output_boundary.names():
            raise PlanRunError("Plan output directory must be fresh and empty")
        case_byte_count, case_sha256 = file_snapshot_beneath(
            case_path,
            root=case_path.parent,
        )
        source_path, source_byte_count, source_sha256 = snapshot_declared_actual_sales(
            case_path
        )
        implementation_files = _implementation_snapshots()
        result = prepare_sales_plan_case(case_path, output_dir)
        status = str(result.get("status", "failed"))
        if status not in {"failed", "passed"}:
            raise PlanRunError(f"Plan returned unsupported status: {status}")
        outputs = _output_receipts(output_boundary)
        _require_unchanged_file(
            case_path,
            byte_count=case_byte_count,
            sha256=case_sha256,
            label="case file",
        )
        _require_unchanged_file(
            source_path,
            byte_count=source_byte_count,
            sha256=source_sha256,
            label="actual sales source",
        )
        if _implementation_snapshots() != implementation_files:
            raise PlanRunError("Plan implementation changed during execution")
        content = {
            "schema_version": "vera.sales_plan_execution.v2",
            "workflow": "sales-plan",
            "recipe_id": RECIPE_ID,
            "engine_version": ENGINE_VERSION,
            "engine_sha256": implementation_files[0]["sha256"],
            "implementation_files": implementation_files,
            "implementation_set_sha256": canonical_json_sha256(implementation_files),
            "case_sha256": case_sha256,
            "source_path": source_path.relative_to(case_path.parent).as_posix(),
            "source_byte_count": source_byte_count,
            "source_sha256": source_sha256,
            "status": status,
            "output_artifacts": outputs,
            "output_set_sha256": canonical_json_sha256(outputs),
            "report_ready": False,
        }
        receipt = {**content, "content_sha256": canonical_json_sha256(content)}
        output_boundary.write_json_exclusive(RECEIPT_NAME, receipt)
        _require_unchanged_file(
            case_path,
            byte_count=case_byte_count,
            sha256=case_sha256,
            label="case file",
        )
        _require_unchanged_file(
            source_path,
            byte_count=source_byte_count,
            sha256=source_sha256,
            label="actual sales source",
        )
        if _implementation_snapshots() != implementation_files:
            raise PlanRunError("Plan implementation changed during execution")
        output_boundary.verify_tracked()
        return receipt


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run one Plan scenario."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="sales-plan",
            input_paths=[args.case],
            output_dir=args.output_dir,
        )
        validate_client_workflow_run(
            context,
            expected_workflow_id="sales-plan",
            input_paths=[declared_actual_sales_path(args.case)],
            output_dir=args.output_dir,
        )
        receipt = run_plan(case_path=args.case, output_dir=args.output_dir)
    except (
        AssuranceContractError,
        OSError,
        PlanRunError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        LOGGER.error("FAILED: %s", exc)
        return 2
    LOGGER.info("sales-plan: %s (%s)", receipt["status"], args.output_dir)
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
