"""Isolated initial intake over the maintained raw Open-item producer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["main"]


def main() -> None:
    """Retain all public outputs; source meaning stays explicitly reviewed."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import raw_input_runner as runner
    from audit_assurance import build_implementation_receipts, validate_assurance_run

    request = json.loads(sys.stdin.read(1_000_001))
    result: dict[str, Any]
    if request["operation"] == "contract":
        result = {
            "roles": sorted(runner.SUPPORTED_SOURCE_ROLES),
            "adapters": sorted(runner.SUPPORTED_ADAPTER_FAMILIES),
            "implementation": build_implementation_receipts(root),
        }
    elif request["operation"] == "prepare":
        context = runner.load_client_engagement_context_file(
            request["context"], expected_workflow_id="open-item-reconciliation"
        )
        produced = runner.run_raw_input_reconciliation(
            input_dir=context["input_dir"],
            prepared_client_engagement=context,
            assumptions=request["assumptions"],
            title=request["title"],
            narrative=request["narrative"],
            language=request["language"],
            output_subdirectory="reconciliation",
        )
        output = Path(produced["run_output_dir"])
        replay = validate_assurance_run(output)
        result = {
            "status": "ready_for_review",
            "assurance_sha256": replay["content_sha256"],
            "checks_pass": produced["checks_pass"],
            "report_ready": replay["gate_register"]["report_ready"],
            "professional_approval": False,
            "run_completed": False,
        }
    elif request["operation"] == "read":
        replay = validate_assurance_run(Path(request["output"]))
        result = {
            "assurance_sha256": replay["content_sha256"],
            "report_ready": replay["gate_register"]["report_ready"],
        }
    else:
        raise ValueError("Unknown Open-item intake operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
