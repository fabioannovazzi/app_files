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

from preparation_contract_kernel import (
    PinnedDirectory,
    canonical_json_sha256,
    file_snapshot_beneath,
    pinned_directory,
)
from prepare_customer_concentration_case import (
    ENGINE_VERSION as CUSTOMER_CONCENTRATION_ENGINE_VERSION,
)
from prepare_customer_concentration_case import (
    RECIPE_ID as CUSTOMER_CONCENTRATION_RECIPE_ID,
)
from prepare_customer_concentration_case import (
    prepare_customer_concentration_case,
)
from prepare_fdd_case import ENGINE_VERSION as FDD_ENGINE_VERSION
from prepare_fdd_case import OUTPUT_NAMES as FDD_OUTPUT_NAMES
from prepare_fdd_case import RECIPE_IDS as FDD_RECIPE_IDS
from prepare_fdd_case import (
    prepare_capex_case,
    prepare_deal_bridges_case,
    prepare_net_debt_case,
    prepare_normalized_working_capital_case,
    prepare_quality_of_earnings_case,
)
from prepare_monthly_pnl_case import ENGINE_VERSION as MONTHLY_PNL_ENGINE_VERSION
from prepare_monthly_pnl_case import RECIPE_ID as MONTHLY_PNL_RECIPE_ID
from prepare_monthly_pnl_case import prepare_monthly_pnl_case
from prepare_working_capital_case import (
    ENGINE_VERSION as WORKING_CAPITAL_ENGINE_VERSION,
)
from prepare_working_capital_case import RECIPE_ID as WORKING_CAPITAL_RECIPE_ID
from prepare_working_capital_case import (
    prepare_working_capital_case,
)

__all__ = ["PACKS", "PackRunError", "main", "run_pack"]

LOGGER = logging.getLogger(__name__)
RECEIPT_NAME = "pack_execution_receipt.json"


class PackRunError(ValueError):
    """Raised when a pack run request is invalid."""


class PackSpec(NamedTuple):
    """Registered deterministic recipe implementation."""

    recipe_id: str
    engine_version: str
    runner: Callable[..., dict[str, Any]]
    implementation_files: tuple[Path, ...]


PLUGIN_ROOT = SCRIPTS_DIR.parent


def _script_path(name: str) -> Path:
    return SCRIPTS_DIR / name


def _vendor_module_path(name: str) -> Path:
    candidates = (
        PLUGIN_ROOT / "vendor" / "modules" / "vera_financial_analysis" / name,
        PLUGIN_ROOT.parent
        / "_shared"
        / "vendor"
        / "modules"
        / "vera_financial_analysis"
        / name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Vera financial-analysis module is unavailable: {name}")


def _vendor_assurance_path(name: str) -> Path:
    candidates = (
        PLUGIN_ROOT / "vendor" / "modules" / "vera_assurance" / name,
        PLUGIN_ROOT.parent / "_shared" / "vendor" / "modules" / "vera_assurance" / name,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"Vera assurance module is unavailable: {name}")


FDD_IMPLEMENTATION_FILES = (
    _script_path("prepare_fdd_case.py"),
    _script_path("run_pack.py"),
    _script_path("preparation_contract_kernel.py"),
    _script_path("validate_case_contracts.py"),
    _vendor_module_path("__init__.py"),
    _vendor_module_path("fdd.py"),
    _vendor_module_path("contracts.py"),
    _vendor_module_path("registry.py"),
    _vendor_assurance_path("__init__.py"),
    _vendor_assurance_path("contracts.py"),
    _vendor_assurance_path("decisions.py"),
    _vendor_assurance_path("envelope.py"),
    _vendor_assurance_path("money.py"),
    _vendor_assurance_path("relationships.py"),
    _vendor_assurance_path("serialization.py"),
)


PACKS: Mapping[str, PackSpec] = {
    "monthly_pnl": PackSpec(
        MONTHLY_PNL_RECIPE_ID,
        MONTHLY_PNL_ENGINE_VERSION,
        prepare_monthly_pnl_case,
        (_script_path("prepare_monthly_pnl_case.py"),),
    ),
    "working_capital": PackSpec(
        WORKING_CAPITAL_RECIPE_ID,
        WORKING_CAPITAL_ENGINE_VERSION,
        prepare_working_capital_case,
        (_script_path("prepare_working_capital_case.py"),),
    ),
    "customer_concentration": PackSpec(
        CUSTOMER_CONCENTRATION_RECIPE_ID,
        CUSTOMER_CONCENTRATION_ENGINE_VERSION,
        prepare_customer_concentration_case,
        (_script_path("prepare_customer_concentration_case.py"),),
    ),
    "quality_of_earnings": PackSpec(
        FDD_RECIPE_IDS["quality_of_earnings"],
        FDD_ENGINE_VERSION,
        prepare_quality_of_earnings_case,
        FDD_IMPLEMENTATION_FILES,
    ),
    "net_debt": PackSpec(
        FDD_RECIPE_IDS["net_debt"],
        FDD_ENGINE_VERSION,
        prepare_net_debt_case,
        FDD_IMPLEMENTATION_FILES,
    ),
    "normalized_working_capital": PackSpec(
        FDD_RECIPE_IDS["normalized_working_capital"],
        FDD_ENGINE_VERSION,
        prepare_normalized_working_capital_case,
        FDD_IMPLEMENTATION_FILES,
    ),
    "capex": PackSpec(
        FDD_RECIPE_IDS["capex"],
        FDD_ENGINE_VERSION,
        prepare_capex_case,
        FDD_IMPLEMENTATION_FILES,
    ),
    "deal_bridges": PackSpec(
        FDD_RECIPE_IDS["deal_bridges"],
        FDD_ENGINE_VERSION,
        prepare_deal_bridges_case,
        FDD_IMPLEMENTATION_FILES,
    ),
}


def _implementation_label(path: Path) -> str:
    if path.parent == SCRIPTS_DIR:
        return f"scripts/{path.name}"
    parts = path.parts
    try:
        modules_position = len(parts) - 1 - tuple(reversed(parts)).index("modules")
    except ValueError:
        return path.name
    return "/".join(parts[modules_position:])


def _implementation_snapshots(
    paths: Sequence[Path],
) -> list[dict[str, Any]]:
    snapshots = []
    for path in paths:
        byte_count, sha256 = file_snapshot_beneath(path, root=path.parent)
        snapshots.append(
            {
                "path": _implementation_label(path),
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
        raise PackRunError(f"{label} changed during pack execution")


def _output_receipts(
    output_boundary: PinnedDirectory,
    *,
    track: bool,
) -> list[dict[str, Any]]:
    receipts = []
    for name in output_boundary.names():
        if name == RECEIPT_NAME:
            raise PackRunError(
                "pack output directory contains an unsupported entry: " f"{name}"
            )
        byte_count, sha256 = output_boundary.snapshot_file(name, track=track)
        receipts.append(
            {
                "artifact_ref": Path(name).stem,
                "path": name,
                "byte_count": byte_count,
                "sha256": sha256,
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
    supplied_case_path = Path(case_path)
    supplied_output_dir = Path(output_dir)
    if supplied_case_path.is_symlink():
        raise PackRunError("case path must be a regular file")
    if supplied_output_dir.is_symlink():
        raise PackRunError("pack output directory cannot be a symlink")
    case_path = supplied_case_path.absolute()
    output_dir = supplied_output_dir.absolute()
    if not case_path.is_file():
        raise PackRunError("case path must be a regular file")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise PackRunError("pack output path must be a directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    is_fdd_pack = pack_id in FDD_RECIPE_IDS
    with pinned_directory(output_dir) as output_boundary:
        if output_boundary.names():
            raise PackRunError("pack output directory must be a fresh empty directory")
        case_byte_count, case_sha256 = file_snapshot_beneath(
            case_path,
            root=case_path.parent,
        )
        implementation_files = _implementation_snapshots(spec.implementation_files)
        try:
            if is_fdd_pack:
                result = spec.runner(
                    case_path,
                    output_dir,
                    output_boundary=output_boundary,
                )
                if result.get("case_file_sha256") != case_sha256:
                    raise PackRunError(
                        "FDD runner did not execute the pre-snapshotted case bytes"
                    )
            else:
                result = spec.runner(case_path, output_dir)
            status = str(result.get("status", "failed"))
            if status not in {"failed", "passed", "qualified"}:
                raise PackRunError(f"pack returned unsupported status: {status}")
            if is_fdd_pack and output_boundary.names() != sorted(FDD_OUTPUT_NAMES):
                raise PackRunError("FDD output directory contains an unsupported entry")
            outputs = _output_receipts(
                output_boundary,
                track=is_fdd_pack,
            )
            _require_unchanged_file(
                case_path,
                byte_count=case_byte_count,
                sha256=case_sha256,
                label="case file",
            )
            if (
                _implementation_snapshots(spec.implementation_files)
                != implementation_files
            ):
                raise PackRunError("implementation files changed during pack execution")
            content = {
                "schema_version": "vera.financial_analysis_pack_execution.v3",
                "pack_id": pack_id,
                "recipe_id": spec.recipe_id,
                "engine_version": spec.engine_version,
                "engine_sha256": implementation_files[0]["sha256"],
                "implementation_files": implementation_files,
                "implementation_set_sha256": canonical_json_sha256(
                    implementation_files
                ),
                "case_sha256": case_sha256,
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
            if (
                _implementation_snapshots(spec.implementation_files)
                != implementation_files
            ):
                raise PackRunError("implementation files changed during pack execution")
            if is_fdd_pack and output_boundary.names() != sorted(
                (*FDD_OUTPUT_NAMES, RECEIPT_NAME)
            ):
                raise PackRunError("FDD output directory contains an unsupported entry")
            output_boundary.verify_tracked()
            return receipt
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            try:
                output_boundary.cleanup_tracked()
            except (OSError, ValueError) as cleanup_error:
                raise PackRunError(
                    f"pack failed and partial-output cleanup failed: {exc}"
                ) from cleanup_error
            raise


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
