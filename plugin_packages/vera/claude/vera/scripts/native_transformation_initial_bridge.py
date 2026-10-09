"""Fixed isolated public synthetic initialization; no model or domain inference."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Keep public initial state and unknown attributes exactly as produced."""
    request = json.loads(sys.stdin.read(2_000_001))
    module, root = Path(request["module"]), Path(request["root"])
    if module.name != "trasformazione":
        raise PermissionError("Unsupported synthetic initialization producer")
    sys.path.insert(0, str(Path(__file__).parent))
    from native_transformation import bounded, files

    sys.path.insert(0, str(module / "scripts"))
    from transform_case import CaseStore

    store = CaseStore(root)
    if request["action"] == "initialize":
        if (files(root) if root.exists() else {}) != request["expected_files"] or (
            root.exists() and any(root.iterdir())
        ):
            raise ValueError("Synthetic target changed or is no longer empty")
        state = store.initialize(
            request["case_id"], request["fields"]["owner"], request["fields"]["purpose"]
        )
    elif request["action"] == "inspect":
        state = store.load()
    else:
        raise ValueError("Unknown synthetic initialization producer action")
    if state["case"]["id"] != request["case_id"] or state["synthetic_only"] is not True:
        raise PermissionError("Synthetic initialization identity changed")
    sys.stdout.write(bounded(state))


if __name__ == "__main__":
    main()
