"""Reseal Report Builder review integrity after an applied review."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__report_builder_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/report-builder"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Report Builder implementation bootstrap is not a real file.")
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
    raise RuntimeError("Report Builder implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_report_builder_implementation_bootstrap",
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

from report_builder_integrity import seal_review_integrity
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seal current Report Builder source and handoff artifacts."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--expected-predecessor-checkpoint")
    args = parser.parse_args()
    try:
        client_context = load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="report-builder",
            output_dir=args.output_dir,
        )
    except AssuranceContractError as exc:
        parser.error(str(exc))
    final_artifacts = json.loads(
        (args.output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    if not isinstance(final_artifacts, dict):
        raise ValueError("final_artifacts.json must be an object")
    if str(final_artifacts.get("run_id") or "") != str(client_context["run_id"]):
        parser.error(
            "final_artifacts.json run_id does not match the customer-run context"
        )
    path = seal_review_integrity(
        args.output_dir,
        run_id=str(final_artifacts.get("run_id") or ""),
        expected_predecessor_checkpoint=args.expected_predecessor_checkpoint,
    )
    integrity = json.loads(path.read_text(encoding="utf-8"))
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "path": path.name,
                "content_sha256": integrity["content_sha256"],
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
