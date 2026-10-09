"""Isolate registered Financial Analysis recipes without substituting their contracts."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Read case-declared lexical bindings or invoke the unchanged managed public CLI."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    import run_pack

    request = json.loads(sys.stdin.read(128001))
    operation = request["operation"]
    if operation == "info":
        result = {
            "packs": {
                key: {
                    "recipe_id": spec.recipe_id,
                    "engine_version": spec.engine_version,
                }
                for key, spec in run_pack.PACKS.items()
            },
            "implementations": {
                key: run_pack._implementation_snapshots(spec.implementation_files)
                for key, spec in run_pack.PACKS.items()
            },
            "scripts": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((root / "scripts").glob("*.py"))
            },
        }
    elif operation == "bindings":
        case = Path(request["case"])
        result = {
            "sources": [
                {
                    "source_id": identity,
                    "locator": path.relative_to(case.parent).as_posix(),
                }
                for identity, path in run_pack.declared_case_input_bindings(
                    case, request["pack_id"]
                )
            ]
        }
    elif operation == "execute":
        status = run_pack.main(
            [
                "--pack",
                request["pack_id"],
                "--case",
                request["case"],
                "--client-engagement",
                request["context"],
                "--output-dir",
                request["output"],
            ]
        )
        receipt = Path(request["output"]) / run_pack.RECEIPT_NAME
        if status not in {0, 1} or not receipt.is_file():
            raise ValueError(
                "Financial Analysis public recipe refused; retained native intent requires recovery"
            )
        result = {"receipt": json.loads(receipt.read_bytes()), "exit_code": status}
    else:
        raise ValueError("Unknown Financial Analysis bridge operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
