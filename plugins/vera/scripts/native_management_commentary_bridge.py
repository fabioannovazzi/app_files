"""Replay public commentary validation and the unchanged normal finalizer."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Keep metric closure and the complete HTML/Markdown in public producers."""
    root = Path(sys.argv[1])
    request = json.loads(sys.stdin.read(128001))
    sys.path.insert(0, str(root / "scripts"))
    for vendor in (root / "vendor/modules", root.parent / "_shared/vendor/modules"):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    import management_control_core as core

    pack = core.load_json(Path(request["pack"]))
    if request["operation"] == "validate":
        checked = core.finalize_commentary(pack, request["commentary"])
        result = {
            "metric_references_checked": True,
            "calculation_status": pack["status"],
            "normalized_commentary": checked,
            "professional_approval": False,
        }
    elif request["operation"] == "finalize":
        import finalize_pack

        with contextlib.redirect_stdout(io.StringIO()):
            code = finalize_pack.main(
                [
                    "--pack",
                    request["pack"],
                    "--commentary",
                    request["commentary"],
                    "--client-engagement",
                    request["context"],
                    "--output-dir",
                    request["output"],
                ]
            )
        if code:
            raise ValueError("The public management finalizer refused the commentary")
        output = Path(request["output"])
        receipt = core.load_json(output / "commentary_receipt.json")
        if (
            receipt["pack_sha256"] != core.sha256_file(Path(request["pack"]))
            or receipt["commentary_sha256"]
            != core.sha256_file(Path(request["commentary"]))
            or any(
                core.sha256_file(output / row["path"]) != row["sha256"]
                for row in receipt["outputs"]
            )
        ):
            raise ValueError("The complete normal management finalization changed")
        result = {"receipt": receipt, "professional_approval": False}
    else:
        raise ValueError("Unknown management commentary operation")
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
