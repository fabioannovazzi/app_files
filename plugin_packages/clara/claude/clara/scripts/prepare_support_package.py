"""Prepare a clean Clara support package for delivery escalation."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

import argparse
import logging
from pathlib import Path

from advisor_case_core import prepare_support_package

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _format_size(byte_count: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(byte_count)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{byte_count} B"


def main() -> int:
    """Run support package export."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--request", required=True)
    parser.add_argument("--requested-by", default="")
    parser.add_argument("--recipient", default="Support reviewer")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = prepare_support_package(
        args.case_dir,
        request=args.request,
        requested_by=args.requested_by,
        recipient=args.recipient,
        package_path=args.out,
    )
    LOGGER.info("Prepared Clara support package: %s", result.package_path)
    LOGGER.info("Support note: %s", result.support_request_archive_path)
    LOGGER.info(
        "Included %s file(s); excluded %s local/runtime file(s), %s.",
        result.included_file_count,
        result.excluded_file_count,
        _format_size(result.excluded_bytes),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
