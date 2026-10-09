"""Fixed offline SARI initialization and inventory through maintained producers."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Resolve actual owned context before creating empty drafts or extracting files."""
    root = Path(sys.argv[1])
    if root.name != "registro-imprese-sari":
        raise PermissionError("Unsupported registry producer")
    sys.path.insert(0, str(root / "scripts"))
    from case_core import load_client_engagement_context_file, load_running_case_context
    from initialize_case import initialize_case
    from inventory_case import inventory_case

    request = json.loads(sys.stdin.read(128001))
    if request["operation"] == "implementation":
        directories = [root / "scripts", root / "assets", root / "schemas"]
        directories += [
            p / "vera_assurance"
            for p in (
                root / "vendor/modules",
                root.parent.parent / "vendor/modules",
                root.parent / "_shared/vendor/modules",
            )
            if (p / "vera_assurance").is_dir()
        ][:1]
        result = {
            str(index)
            + "/"
            + path.relative_to(directory)
            .as_posix(): hashlib.sha256(path.read_bytes())
            .hexdigest()
            for index, directory in enumerate(directories)
            for path in sorted(directory.rglob("*"))
            if path.is_file() and path.suffix in {".py", ".json"}
        }
    elif request["operation"] == "prepare":
        context_path = Path(request["context"])
        selected = load_client_engagement_context_file(
            context_path,
            expected_workflow_id="registro-imprese-sari",
            allowed_statuses=("running",),
        )
        context = load_running_case_context(
            context_path, output_dir=Path(selected["output_dir"])
        )
        output = Path(context["output_dir"])
        if any(output.iterdir()):
            raise ValueError("Existing SARI outputs require the ordinary continuation")
        fields = request["fields"]
        initialize_case(
            output,
            run_id=context["run_id"],
            reference_date=fields["reference_date"],
            client_reference=fields["client_reference"],
            language=fields["language"],
            jurisdiction=fields["jurisdiction"],
            client_engagement=context_path,
        )
        inventory = inventory_case(
            Path(context["input_dir"]),
            output,
            run_id=context["run_id"],
            language=fields["language"],
            use_ocr=False,
            allow_ocr_model_download=False,
            client_engagement=context_path,
            run_root=Path(context["run_root"]),
        )
        result = {
            "status": inventory["status"],
            "run_id": context["run_id"],
            "document_count": inventory["document_count"],
            "semantic_decisions_performed": False,
            "network_calls_performed": False,
            "professional_review": "pending",
            "ready_to_file": False,
        }
    else:
        raise ValueError("Unsupported registry intake operation")
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
