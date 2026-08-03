from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__journal_sampling_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/journal-sampling"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Journal Sampling implementation bootstrap is not a real file.")
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
    raise RuntimeError("Journal Sampling implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_journal_sampling_implementation_bootstrap",
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
import sys
from pathlib import Path

from journal_sampling_core import (
    finalize_sample_review_successor,
    prepare_sample_review_successor,
    validate_sample_assurance,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Internal Journal Sampling review-successor assurance bridge."
    )
    parser.add_argument(
        "command", choices=("context", "validate", "prepare", "finalize")
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--kind", choices=("save", "apply"))
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument(
        "--persistent-output-dir",
        type=Path,
        help=argparse.SUPPRESS,
    )
    return parser


def _is_ephemeral_review_working_tree(path: Path, *, run_root: Path) -> bool:
    try:
        relative = path.relative_to(run_root)
    except ValueError:
        return False
    return (
        len(relative.parts) == 2
        and relative.parts[0].startswith(".generated-review-transaction-")
        and relative.parts[1] == "working"
    )


def _load_cli_customer_run(args: argparse.Namespace) -> dict[str, object]:
    context = load_client_engagement_context_file(
        args.client_engagement,
        expected_workflow_id="journal-sampling",
    )
    expected_output = Path(str(context["output_dir"]))
    persistent_output = (
        Path(args.persistent_output_dir).expanduser().resolve()
        if args.persistent_output_dir is not None
        else expected_output
    )
    if persistent_output.expanduser().resolve() != expected_output:
        raise AssuranceContractError(
            "persistent assurance output must be the customer run output root"
        )
    load_client_engagement_context_file(
        args.client_engagement,
        expected_workflow_id="journal-sampling",
        output_dir=persistent_output,
    )
    actual_output = args.output_dir.expanduser().resolve(strict=True)
    if actual_output == expected_output or actual_output.is_relative_to(
        expected_output
    ):
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="journal-sampling",
            input_paths=[actual_output],
            output_dir=actual_output,
        )
        return context
    if not _is_ephemeral_review_working_tree(
        actual_output,
        run_root=Path(str(context["run_root"])),
    ):
        raise AssuranceContractError(
            "assurance input is outside the customer run and its ephemeral review tree"
        )
    return context


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        context = _load_cli_customer_run(args)
    except (AssuranceContractError, OSError) as exc:
        parser.error(str(exc))
    if args.command == "context":
        result = {
            "ok": True,
            "workflow_id": context["workflow_id"],
            "run_id": context["run_id"],
        }
    elif args.command == "validate":
        result = validate_sample_assurance(args.output_dir)
    elif args.command == "prepare":
        if args.kind is None:
            raise ValueError("--kind is required for successor preparation.")
        result = prepare_sample_review_successor(args.output_dir, kind=args.kind)
    else:
        if args.kind is None:
            raise ValueError("--kind is required for successor finalization.")
        result = finalize_sample_review_successor(args.output_dir, kind=args.kind)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
