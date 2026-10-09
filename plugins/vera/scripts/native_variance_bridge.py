"""Isolated unchanged public variance execution and exact implementation identity."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Keep arithmetic, charts, accounting readiness and reports in the producer."""
    root = Path(sys.argv[1])
    request = json.loads(sys.stdin.read(64001))
    sys.path.insert(0, str(root / "scripts"))
    import run_variance
    import vera_assurance

    if request["operation"] == "contract":
        legacy = root / "vendor"
        shared = root.parent / "_shared/variance/vendor"
        if (shared / "modules/__init__.py").is_file():
            legacy = shared
        populations = {
            "component": root,
            "legacy": legacy,
            "assurance": Path(vera_assurance.__file__).parent,
        }
        result = {
            "files": {
                label
                + "/"
                + p.relative_to(parent)
                .as_posix(): hashlib.sha256(p.read_bytes())
                .hexdigest()
                for label, parent in populations.items()
                for p in sorted(parent.rglob("*"))
                if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts
            }
        }
    elif request["operation"] == "inspect":
        import inspect_inputs

        sys.argv = [
            str(root / "scripts/inspect_inputs.py"),
            request["source"],
            "--output-dir",
            request["output"],
            "--client-engagement",
            request["context"],
            "--language",
            request["language"],
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            code = inspect_inputs.main()
        if code:
            raise ValueError("Public variance input inspection did not complete")
        result = {"inspection_written": True, "calculated": False}
    elif request["operation"] == "prepare":
        sys.argv = [str(root / "scripts/check_dependencies.py")]
        import check_dependencies

        with contextlib.redirect_stdout(io.StringIO()) as diagnostics:
            code = check_dependencies.main()
        if code:
            raise ValueError(diagnostics.getvalue().strip())
        import inspect_inputs

        inspection = Path(request["output"]) / "inspection"
        sys.argv = [
            str(root / "scripts/inspect_inputs.py"),
            request["source"],
            "--recipe",
            request["recipe"],
            "--output-dir",
            str(inspection),
            "--client-engagement",
            request["context"],
            "--language",
            request["language"],
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            code = inspect_inputs.main()
        if code:
            raise ValueError("Public variance input inspection did not complete")
        sys.argv = [
            str(root / "scripts/run_variance.py"),
            request["source"],
            "--recipe",
            request["recipe"],
            "--output-dir",
            request["output"],
            "--client-engagement",
            request["context"],
            "--currency",
            request["currency"],
            "--language",
            request["language"],
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            code = run_variance.main()
        if code:
            raise ValueError("Public variance execution did not complete normally")
        output = Path(request["output"])
        review_payload = json.loads((output / "review_payload.json").read_bytes())
        checked = subprocess.run(
            [request["node"], str(root / "mcp/server.cjs")],
            input=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "validate_variance_analysis_review",
                        "arguments": {
                            "review_payload": review_payload,
                            "run_intake": json.loads(
                                (output / "run_intake.json").read_bytes()
                            ),
                            "ui_decisions": json.loads(
                                (output / "ui_decisions.json").read_bytes()
                            ),
                            "final_artifacts": json.loads(
                                (output / "final_artifacts.json").read_bytes()
                            ),
                            "client_engagement": request["context"],
                        },
                    },
                }
            )
            + "\n",
            text=True,
            capture_output=True,
            timeout=35,
            env={**os.environ, "PYTHON": sys.executable},
            check=False,
        )
        if checked.returncode:
            raise ValueError(
                checked.stderr.strip() or "Public variance review validation failed"
            )
        validated = json.loads(checked.stdout)["result"]
        if validated.get("isError"):
            raise ValueError(validated["content"][0]["text"])
        result = {
            "review_payload_validated": True,
            "final_artifacts": json.loads(
                (output / "final_artifacts.json").read_bytes()
            ),
            "summary": json.loads(
                (output / "standard_variance_context.json").read_bytes()
            ),
        }
    else:
        raise ValueError("Unknown variance producer operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
