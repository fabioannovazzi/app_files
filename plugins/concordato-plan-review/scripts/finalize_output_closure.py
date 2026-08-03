"""Seal a Concordato output successor after an authorized review transaction."""

from __future__ import annotations

import sys as _bootstrap_sys  # isort: skip

_bootstrap_sys.dont_write_bytecode = True
_bootstrap_sys.pycache_prefix = (
    r"Z:\__concordato_no_bytecode__"
    if _bootstrap_sys.platform == "win32"
    else "/dev/null/concordato-plan-review"
)

import os as _bootstrap_os  # isort: skip

_BOOTSTRAP_PATH = _bootstrap_os.path.join(
    _bootstrap_os.path.dirname(_bootstrap_os.path.abspath(__file__)),
    "implementation_bootstrap.py",
)
_BOOTSTRAP_ENTRY = _bootstrap_os.lstat(_BOOTSTRAP_PATH)
if _BOOTSTRAP_ENTRY.st_mode & 0o170000 != 0o100000 or _BOOTSTRAP_ENTRY.st_nlink != 1:
    raise RuntimeError("Concordato implementation bootstrap is not a real file.")
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
    raise RuntimeError("Concordato implementation bootstrap changed while read.")
_BOOTSTRAP_NAMESPACE = {
    "__file__": _BOOTSTRAP_PATH,
    "__name__": "_concordato_implementation_bootstrap",
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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from concordato_plan_core import (
    ASSURANCE_IMPLEMENTATION_ROOT,
    COMPONENT_ROOT,
    validate_numeric_evidence_closure,
)
from output_closure import finalize_output_closure, refresh_final_artifact_index
from replay_assurance import _current_source_root
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    canonical_json_sha256,
    load_client_engagement_context_file,
    validate_assurance_envelope,
)

__all__ = ["main"]


def _read_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must be a JSON object")
    return payload


def _load_cli_customer_context(
    *,
    client_engagement: Path,
    output_dir: Path,
    persistent_output_dir: Path | None,
) -> dict[str, Any]:
    """Authorize either the canonical output or its MCP transaction copy."""

    context = load_client_engagement_context_file(
        client_engagement,
        expected_workflow_id="concordato-plan-review",
    )
    expected_output = Path(str(context["output_dir"])).resolve()
    persistent_output = (
        persistent_output_dir.expanduser().resolve()
        if persistent_output_dir is not None
        else expected_output
    )
    if persistent_output != expected_output:
        raise AssuranceContractError(
            "persistent Concordato output must be the customer run output root"
        )
    actual_output = output_dir.expanduser().resolve(strict=True)
    if actual_output == expected_output or actual_output.is_relative_to(
        expected_output
    ):
        load_client_engagement_context_file(
            client_engagement,
            expected_workflow_id="concordato-plan-review",
            output_dir=actual_output,
        )
        return context
    try:
        relative = actual_output.relative_to(Path(str(context["run_root"])))
    except ValueError as exc:
        raise AssuranceContractError(
            "Concordato output is outside the customer run"
        ) from exc
    if not (
        len(relative.parts) == 2
        and relative.parts[0].startswith(".generated-review-transaction-")
        and relative.parts[1] == "working"
    ):
        raise AssuranceContractError(
            "Concordato output is outside the customer run and its review transaction"
        )
    return context


def _replay_successor_prerequisites(
    output_dir: Path,
    client_context: Mapping[str, Any] | None = None,
) -> None:
    """Freshly replay immutable authority before sealing a mutable successor."""

    run_intake = _read_object(output_dir / "run_intake.json")
    review_payload = _read_object(output_dir / "review_payload.json")
    envelope = _read_object(output_dir / "assurance_envelope.json")
    source_root = _current_source_root(output_dir, run_intake, client_context)
    review_content = dict(review_payload)
    review_digest = review_content.pop("content_sha256", None)
    if review_digest != canonical_json_sha256(review_content):
        raise ValueError("Persisted review payload digest is stale")
    validated = validate_assurance_envelope(
        envelope,
        artifact_roots={
            "source": source_root,
            "run": output_dir,
            "implementation": COMPONENT_ROOT,
            "assurance_implementation": ASSURANCE_IMPLEMENTATION_ROOT,
        },
    )
    assurance = review_payload.get("assurance")
    if (
        not isinstance(assurance, dict)
        or assurance.get("envelope_content_sha256") != validated["content_sha256"]
        or assurance.get("final_ready") is not False
    ):
        raise ValueError("Review payload assurance binding is stale")
    ledger = _read_object(output_dir / "numeric_evidence_ledger.json")
    if ledger.get("schema_version") == "concordato.numeric_evidence_ledger.v2":
        validate_numeric_evidence_closure(
            output_dir,
            ledger,
            source_root=source_root,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--persistent-output-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--phase",
        required=True,
        choices=("review_save_finalization", "review_apply_finalization"),
    )
    args = parser.parse_args()
    try:
        output_dir = Path(args.output_dir).resolve()
        client_context = _load_cli_customer_context(
            client_engagement=args.client_engagement,
            output_dir=output_dir,
            persistent_output_dir=args.persistent_output_dir,
        )
        _replay_successor_prerequisites(output_dir, client_context)
        refresh_final_artifact_index(output_dir)
        closure = finalize_output_closure(
            output_dir,
            phase=args.phase,
        )
    except (AssuranceContractError, OSError, ValueError) as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}) + "\n")
        return 1
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "phase": closure["phase"],
                "content_sha256": closure["content_sha256"],
                "declared_path_count": len(closure["declared_paths"]),
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
