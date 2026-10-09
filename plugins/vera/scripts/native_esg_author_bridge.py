"""Fixed ESG proposal preview and public execution; no semantic decisions."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Execute maintained contracts; preview redirects only verified local outputs."""
    root = Path(sys.argv[1])
    if root.name != "esg-reporting-assurance":
        raise PermissionError("Unsupported ESG producer")
    sys.path.insert(0, str(root / "scripts"))
    import esg_case as esg

    value = json.loads(sys.stdin.read(128001))
    context_path = Path(value["context"])
    command = value["command"]
    if command not in {
        "start_case",
        "bind_evidence",
        "register_source",
        "record_decision",
        "build_deliverables",
    }:
        raise ValueError("Unsupported ESG command")
    original_context = esg._context
    context = original_context(context_path)
    output = Path(context["output_dir"])
    if value["operation"] == "preview":
        # The unchanged execute owns schema, parsing, history and draft rendering.
        # A preview writes only an isolated temporary copy, never official output.
        with tempfile.TemporaryDirectory(
            prefix="vera-native-esg-preview-"
        ) as directory:
            target = Path(directory).resolve(strict=True)
            if (output / "esg_state.json").exists():
                esg.resume_case(context_path)
            for path in [output / "esg_state.json", *output.glob("esg-draft-*")]:
                if not path.exists():
                    continue
                if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                    raise PermissionError("ESG preview requires ordinary originals")
                (target / path.name).write_bytes(path.read_bytes())

            def preview_context(path: Path, *, reading: bool = False) -> dict:
                verified = original_context(path, reading=reading)
                if path.resolve() == context_path.resolve():
                    verified = {**verified, "output_dir": str(target)}
                return verified

            esg._context = preview_context
            result = esg.execute(context_path, command, value["request"])
            summary = esg.resume_case(context_path)
            selected = next(
                r for r in summary["objects"] if r["reference"] == result["reference"]
            )
            result = {
                "reference": result["reference"],
                "object": selected,
                "summary": summary,
            }
    elif value["operation"] == "apply":
        result = esg.execute(context_path, command, value["request"])
        summary = esg.resume_case(context_path)
        selected = next(
            r for r in summary["objects"] if r["reference"] == result["reference"]
        )
        result = {"result": result, "object": selected}
    else:
        raise ValueError("Unsupported ESG producer operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
