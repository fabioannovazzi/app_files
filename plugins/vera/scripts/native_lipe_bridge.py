"""Isolated execution of the unchanged, durable LIPE calculation CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Return engine identity or the single newly persisted calculation revision."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    from lipe_core import engine_hash, rules_hash

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        result = {"engine": engine_hash(), "rules": rules_hash()}
    elif request["operation"] == "calculate":
        from lipe import main as calculate_cli

        output = Path(request["output"])
        before = set(output.glob("lipe-*"))
        status = calculate_cli(
            [
                "calculate",
                "--case",
                request["case"],
                "--client-engagement",
                request["context"],
                "--source-root",
                request["source_root"],
                "--output",
                request["output"],
            ]
        )
        created = set(output.glob("lipe-*")) - before
        if status not in {0, 2} or len(created) != 1:
            raise ValueError("LIPE did not persist exactly one calculation revision")
        result = {"generation": created.pop().name, "exit_status": status}
    else:
        raise ValueError("Unknown LIPE bridge operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
