"""Inspect bank and journal inputs for deterministic Codex reconciliation."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__journal_bank_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/journal-bank-reconciliation"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Journal–Bank implementation bootstrap is not a real file.")
with open(_BOOTSTRAP_PATH, "rb") as _bootstrap_handle:
    _BOOTSTRAP_BEFORE = _bootstrap_os.fstat(_bootstrap_handle.fileno())
    _BOOTSTRAP_BYTES = _bootstrap_handle.read()
    _BOOTSTRAP_AFTER = _bootstrap_os.fstat(_bootstrap_handle.fileno())
_BOOTSTRAP_IDENTITY = (
    _BOOTSTRAP_ENTRY.st_dev,
    _BOOTSTRAP_ENTRY.st_ino,
    _BOOTSTRAP_ENTRY.st_size,
    _BOOTSTRAP_ENTRY.st_mtime_ns,
)
if (
    _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_BEFORE.st_dev,
        _BOOTSTRAP_BEFORE.st_ino,
        _BOOTSTRAP_BEFORE.st_size,
        _BOOTSTRAP_BEFORE.st_mtime_ns,
    )
    or _BOOTSTRAP_IDENTITY
    != (
        _BOOTSTRAP_AFTER.st_dev,
        _BOOTSTRAP_AFTER.st_ino,
        _BOOTSTRAP_AFTER.st_size,
        _BOOTSTRAP_AFTER.st_mtime_ns,
    )
    or len(_BOOTSTRAP_BYTES) != _BOOTSTRAP_AFTER.st_size
):
    raise RuntimeError("Journal–Bank implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_journal_bank_implementation_bootstrap",
}
# The exact stable single-link bootstrap source is verified above.
exec(  # nosec B102
    compile(_BOOTSTRAP_BYTES, _BOOTSTRAP_PATH, "exec"), _BOOTSTRAP_NAMESPACE
)
_BOOTSTRAP_NAMESPACE["activate_implementation_boundary"]()
_SCRIPTS_DIR = _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__))
if _SCRIPTS_DIR not in _bootstrap_sys.path:
    _bootstrap_sys.path.insert(0, _SCRIPTS_DIR)

import argparse
import json
import logging
from pathlib import Path

from journal_bank_core import (
    add_common_args,
    configure_logging,
    inspect_inputs,
    log_execution_status,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run input inspection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", type=Path, help="Bank statement file or folder.")
    parser.add_argument("journal", type=Path, help="Journal/ledger file or folder.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where inspection.json and suggested_recipe.json will be written.",
    )
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--sample", type=Path, help="Optional sample movements file.")
    parser.add_argument("--recipe", type=Path, help="Optional existing recipe JSON.")
    parser.add_argument("--pdf-side", choices=("bank", "journal"), default="journal")
    parser.add_argument(
        "--pdf-source",
        type=Path,
        help="Exact PDF inside the selected bound source folder.",
    )
    from vera_journal_pdf.recovery import add_recovery_args

    add_recovery_args(parser)
    add_common_args(parser)
    args = parser.parse_args()
    configure_logging(args.verbose)

    input_paths = [args.bank, args.journal]
    input_paths.extend(path for path in (args.sample, args.recipe) if path is not None)
    try:
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="journal-bank-reconciliation",
            input_paths=input_paths,
            output_dir=args.output_dir,
        )
    except AssuranceContractError as exc:
        LOGGER.error("CLIENT_ENGAGEMENT_BLOCKED: %s", exc)
        return 2

    if args.pdf_recovery:
        if not args.pdf_currency:
            parser.error("--pdf-currency is required for recovery")
        from vera_journal_pdf.recovery import recover_pdf

        recipe = json.loads(args.recipe.read_text()) if args.recipe else {}
        selected_root = args.bank if args.pdf_side == "bank" else args.journal
        selected = args.pdf_source or selected_root
        if selected_root.is_dir():
            if (
                not selected.is_file()
                or selected_root.resolve() not in selected.resolve().parents
            ):
                parser.error(
                    "--pdf-source must select one PDF inside the bound source folder"
                )
            source_name = (
                selected.resolve().relative_to(selected_root.resolve()).as_posix()
            )
        else:
            if selected.resolve() != selected_root.resolve():
                parser.error("--pdf-source differs from the bound source file")
            source_name = selected_root.name
        if any(p.is_symlink() for p in (selected, *selected.parents)):
            parser.error("Recovery source must not traverse symlinks")
        layout_key = (
            "pdf_bank_layout" if args.pdf_side == "bank" else "pdf_registration_layout"
        )
        entry = recipe.get(args.pdf_side, {}).get("files", {}).get(source_name, {})
        result = recover_pdf(
            selected,
            args.output_dir,
            args.pdf_recovery,
            currency=args.pdf_currency,
            layout=entry.get(layout_key),
            pages=args.pdf_pages,
            region=args.pdf_region,
            reason=args.pdf_reason,
            render=args.pdf_render,
            source_role=args.pdf_side,
        )
        LOGGER.info("%s", json.dumps(result, ensure_ascii=False))
        return 0

    result = inspect_inputs(
        args.bank,
        args.journal,
        args.output_dir,
        args.recipe,
        sample_path=args.sample,
        language=args.language,
        document_language=args.document_language,
    )
    log_execution_status(args.output_dir, "bank_rows=%s", result.bank["row_count"])
    log_execution_status(
        args.output_dir, "journal_rows=%s", result.journal["row_count"]
    )
    log_execution_status(
        args.output_dir, "sample_movements=%s", result.sample["movement_count"]
    )
    log_execution_status(
        args.output_dir, "wrote %s", args.output_dir / "inspection.json"
    )
    log_execution_status(
        args.output_dir, "wrote %s", args.output_dir / "suggested_recipe.json"
    )
    return 0


if __name__ == "__main__":
    from vera_assurance.contracts import run_recorded_cli

    raise SystemExit(run_recorded_cli(main, Path(__file__)))
