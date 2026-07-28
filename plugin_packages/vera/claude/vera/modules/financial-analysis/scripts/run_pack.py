#!/usr/bin/env python3
"""Run one registered Vera financial-analysis preparation pack."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from preparation_contract_kernel import canonical_json_sha256, file_sha256, write_json
from prepare_customer_concentration_case import (
    ENGINE_VERSION as CUSTOMER_CONCENTRATION_ENGINE_VERSION,
)
from prepare_customer_concentration_case import (
    RECIPE_ID as CUSTOMER_CONCENTRATION_RECIPE_ID,
)
from prepare_customer_concentration_case import prepare_customer_concentration_case
from prepare_monthly_pnl_case import ENGINE_VERSION as MONTHLY_PNL_ENGINE_VERSION
from prepare_monthly_pnl_case import RECIPE_ID as MONTHLY_PNL_RECIPE_ID
from prepare_monthly_pnl_case import prepare_monthly_pnl_case
from prepare_working_capital_case import (
    ENGINE_VERSION as WORKING_CAPITAL_ENGINE_VERSION,
)
from prepare_working_capital_case import RECIPE_ID as WORKING_CAPITAL_RECIPE_ID
from prepare_working_capital_case import prepare_working_capital_case

__all__ = ["PACKS", "PackRunError", "main", "run_pack"]

LOGGER = logging.getLogger(__name__)
RECEIPT_NAME = "pack_execution_receipt.json"


class PackRunError(ValueError):
    """Raised when a pack run request is invalid."""


class PackSpec(NamedTuple):
    """Registered deterministic recipe implementation."""

    recipe_id: str
    engine_version: str
    runner: Callable[[Path, Path], dict[str, Any]]
    engine_file: str


PACKS: Mapping[str, PackSpec] = {
    "monthly_pnl": PackSpec(
        MONTHLY_PNL_RECIPE_ID,
        MONTHLY_PNL_ENGINE_VERSION,
        prepare_monthly_pnl_case,
        "prepare_monthly_pnl_case.py",
    ),
    "working_capital": PackSpec(
        WORKING_CAPITAL_RECIPE_ID,
        WORKING_CAPITAL_ENGINE_VERSION,
        prepare_working_capital_case,
        "prepare_working_capital_case.py",
    ),
    "customer_concentration": PackSpec(
        CUSTOMER_CONCENTRATION_RECIPE_ID,
        CUSTOMER_CONCENTRATION_ENGINE_VERSION,
        prepare_customer_concentration_case,
        "prepare_customer_concentration_case.py",
    ),
}


def _output_receipts(output_dir: Path) -> list[dict[str, Any]]:
    receipts = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.is_symlink() or path.name == RECEIPT_NAME:
            raise PackRunError(
                "pack output directory contains an unsupported entry: " f"{path.name}"
            )
        receipts.append(
            {
                "artifact_ref": path.stem,
                "path": path.name,
                "byte_count": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return receipts


def run_pack(
    *,
    pack_id: str,
    case_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run a registered recipe and write its deterministic execution receipt."""

    try:
        spec = PACKS[pack_id]
    except KeyError as exc:
        raise PackRunError(f"unregistered financial-analysis pack: {pack_id}") from exc
    case_path = case_path.resolve()
    output_dir = output_dir.resolve()
    if not case_path.is_file() or case_path.is_symlink():
        raise PackRunError("case path must be a regular file")
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / RECEIPT_NAME
    receipt_path.unlink(missing_ok=True)

    result = spec.runner(case_path, output_dir)
    status = str(result.get("status", "failed"))
    if status not in {"failed", "passed"}:
        raise PackRunError(f"pack returned unsupported status: {status}")
    outputs = _output_receipts(output_dir)
    engine_path = Path(__file__).resolve().with_name(spec.engine_file)
    content = {
        "schema_version": "vera.financial_analysis_pack_execution.v1",
        "pack_id": pack_id,
        "recipe_id": spec.recipe_id,
        "engine_version": spec.engine_version,
        "engine_sha256": file_sha256(engine_path),
        "case_sha256": file_sha256(case_path),
        "status": status,
        "output_artifacts": outputs,
        "output_set_sha256": canonical_json_sha256(outputs),
        "report_ready": False,
    }
    receipt = {**content, "content_sha256": canonical_json_sha256(content)}
    write_json(receipt_path, receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run one registered pack."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", choices=sorted(PACKS), required=True)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = run_pack(
            pack_id=args.pack,
            case_path=args.case,
            output_dir=args.output_dir,
        )
    except (KeyError, OSError, PackRunError, TypeError, ValueError) as exc:
        LOGGER.error("FAILED: %s", exc)
        return 2
    LOGGER.info(
        "%s: %s (%s)",
        receipt["pack_id"],
        receipt["status"],
        args.output_dir,
    )
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
