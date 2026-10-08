#!/usr/bin/env python3
"""Run the source-bound annual statements recipe in a financial-analysis run."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from annual_statements import analyse, source_paths  # noqa: E402
from annual_statements_render import render_outputs  # noqa: E402
from check_dependencies import _activate_assurance  # noqa: E402
from preparation_contract_kernel import (  # noqa: E402
    canonical_json_sha256,
    file_snapshot_beneath,
    strict_json_snapshot_beneath,
)

_activate_assurance()
from vera_assurance import (  # noqa: E402
    load_client_engagement_context_file,
    validate_client_workflow_run,
)

__all__ = ["run_annual_statements", "main"]
LOGGER = logging.getLogger(__name__)


def _json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def run_annual_statements(
    case_path: Path, output_dir: Path, client_engagement: Path
) -> dict[str, Any]:
    """Validate managed inputs, calculate and render once into a new directory."""
    context = load_client_engagement_context_file(
        client_engagement,
        expected_workflow_id="financial-analysis",
        input_paths=[case_path],
        output_dir=output_dir,
    )
    case, _size, case_hash = strict_json_snapshot_beneath(
        case_path, root=case_path.parent
    )
    paths = source_paths(case, case_path.parent)
    validate_client_workflow_run(
        context,
        expected_workflow_id="financial-analysis",
        input_paths=list(paths.values()),
        output_dir=output_dir,
    )
    bindings = {item["binding_id"]: item for item in context["input_bindings"]}
    for source in case["sources"].values():
        binding = bindings.get(source.get("input_binding_id"))
        if binding is None or source["sha256"] != binding["sha256"]:
            raise ValueError(
                "Annual source must bind one exact imported input and hash"
            )
    implementation_paths = [
        SCRIPT_ROOT / name
        for name in (
            "annual_statements.py",
            "annual_statements_render.py",
            "run_annual_statements.py",
            "preparation_contract_kernel.py",
        )
    ]
    implementation = {
        p.name: file_snapshot_beneath(p, root=SCRIPT_ROOT)[1]
        for p in implementation_paths
    }
    result = analyse(case, case_path.parent)
    outputs = render_outputs(result)
    outputs["annual_result.json"] = _json(result)
    outputs["used_case.json"] = _json(case)
    outputs["reconciliation.json"] = _json(
        {
            "status": result["status"],
            "checks": result["checks"],
            "tolerance": result["tolerance"],
            "source_tie_out": result["source_tie_out"],
        }
    )
    # Validate inputs again before delivery. The final receipt is written last;
    # without it a partial directory can never be represented as a completed run.
    if strict_json_snapshot_beneath(case_path, root=case_path.parent)[2] != case_hash:
        raise ValueError("Annual case changed during calculation")
    for key, path in paths.items():
        if (
            file_snapshot_beneath(path, root=case_path.parent)[1]
            != case["sources"][key]["sha256"]
        ):
            raise ValueError("Annual source changed during calculation")
    if any(
        file_snapshot_beneath(p, root=SCRIPT_ROOT)[1] != implementation[p.name]
        for p in implementation_paths
    ):
        raise ValueError("Annual implementation changed during calculation")
    receipt = {
        "schema_version": "vera.annual_statements_execution.v1",
        "recipe_id": result["recipe_id"],
        "case_sha256": case_hash,
        "implementation": implementation,
        "sources": case["sources"],
        "status": result["status"],
        "report_ready": False,
        "output_artifacts": [
            {
                "path": name,
                "byte_count": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(outputs.items())
        ],
    }
    receipt["content_sha256"] = canonical_json_sha256(receipt)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in outputs.items():
        with (output_dir / name).open("xb") as stream:
            stream.write(content)
    with (output_dir / "annual_execution_receipt.json").open("xb") as stream:
        stream.write(_json(receipt))
    return receipt


def main(argv: list[str] | None = None) -> int:
    """Execute the managed file route shared by Codex and Cowork."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = run_annual_statements(
            args.case, args.output_dir, args.client_engagement
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        LOGGER.error("FAILED: %s", exc)
        return 2
    LOGGER.info(
        "Annual statements: %s; reviewable output in %s",
        receipt["status"],
        args.output_dir,
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
