"""Call the maintained Open-item browser service under its own transaction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """The parent supplies registered source; UI cannot supply a module path."""
    sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
    import review_server

    request = json.loads(sys.stdin.read(128_001))
    if request["operation"] == "read":
        result = review_server.build_session_payload(
            Path(request["output_dir"]), for_display=True
        )
    elif request["operation"] == "regenerate":
        from raw_input_runner import (
            load_client_engagement_context_file,
            regenerate_raw_input_reconciliation,
        )

        context = load_client_engagement_context_file(
            request["context"], expected_workflow_id="open-item-reconciliation"
        )
        result = regenerate_raw_input_reconciliation(
            Path(request["output_dir"]),
            context,
            expected_predecessor_checkpoint=request["arguments"][
                "expected_predecessor_checkpoint"
            ],
        )
    else:
        operation = {
            "save": review_server.save_decisions,
            "apply": review_server.apply_decisions,
        }[request["operation"]]
        result = operation(Path(request["output_dir"]), request["arguments"])
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
