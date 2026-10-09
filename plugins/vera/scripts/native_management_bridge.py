"""Isolated existing management reporting/costing producers and receipt checks."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Keep calculations, context projection and rendering in maintained producers."""
    root = Path(sys.argv[1])
    request = json.loads(sys.stdin.read(512001))
    sys.path.insert(0, str(root / "scripts"))
    for vendor in (root / "vendor/modules", root.parent / "_shared/vendor/modules"):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    import management_control_core as core
    import vera_assurance

    operation = request["operation"]
    if operation == "contract":
        result = {
            "files": {
                label
                + "/"
                + path.relative_to(parent)
                .as_posix(): hashlib.sha256(path.read_bytes())
                .hexdigest()
                for label, parent in (
                    ("component", root),
                    ("assurance", Path(vera_assurance.__file__).parent),
                )
                for path in sorted(parent.rglob("*"))
                if path.is_file()
                and path.suffix != ".pyc"
                and "__pycache__" not in path.parts
            }
        }
    elif operation == "prepare":
        import check_dependencies
        import run_costing
        import run_pack

        if check_dependencies.main([]):
            raise ValueError("Published management runtime dependencies are required")
        arguments = [item for value in request["inputs"] for item in ("--input", value)]
        arguments.extend(
            [
                "--case" if request["mode"] == "costing" else "--recipe",
                request["recipe"],
                "--client-engagement",
                request["context"],
                "--output-dir",
                request["output"],
            ]
        )
        producer = run_costing if request["mode"] == "costing" else run_pack
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = producer.main(arguments)
        output = Path(request["output"])
        pack = core.load_json(output / "management_control_pack.json")
        model = core.load_json(output / "model_context.json")
        receipt = core.load_json(output / "model_context_receipt.json")
        if receipt != core.build_model_context_receipt(pack, model):
            raise ValueError(
                "Management model context receipt differs from public replay"
            )
        if exit_code not in {0, 2} or (exit_code == 2) != (pack["status"] == "blocked"):
            raise ValueError(
                "Management producer did not reach an ordinary output status"
            )
        result = {
            "status": pack["status"],
            "ordinary_exit_code": exit_code,
            "context_receipt_verified": True,
            "coverage": pack["coverage"],
            "controls": pack["controls"],
            "report_status": "draft_pending_professional_review",
        }
    elif operation == "context":
        output = Path(request["output"])
        pack = core.load_json(output / "management_control_pack.json")
        model = core.load_json(output / "model_context.json")
        receipt = core.load_json(output / "model_context_receipt.json")
        if receipt != core.build_model_context_receipt(pack, model):
            raise ValueError(
                "Management bounded context changed or failed public replay"
            )
        result = {
            "model_context": model,
            "model_context_receipt": receipt,
            "execution_receipt": core.load_json(output / "execution_receipt.json"),
            "commentary_template": core.load_json(output / "commentary_template.json"),
            "actual_model_reads_verified": False,
            "record_actual_model_reads_in_run_report": True,
            "professional_approval": False,
            "run_completed": False,
        }
    else:
        raise ValueError("Unknown management bridge operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
