"""Isolated, unchanged Rating producer; no semantic qualification or approval."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Validate portable authority before exposing the complete prepared dossier."""
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / "scripts"))
    for vendor in (
        root / "vendor/modules",
        root.parent.parent / "vendor/modules",
        root.parent / "_shared/vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    import rating_case
    from vera_assurance import load_client_engagement_context_file

    request = json.loads(sys.stdin.read(2_000_001))
    case_path = Path(request["case"])
    case = json.loads(case_path.read_text(encoding="utf-8"))
    previous_path = Path(request["previous"]) if request["previous"] else None
    previous = (
        json.loads(previous_path.read_text(encoding="utf-8")) if previous_path else None
    )
    paths = [case_path, *([previous_path] if previous_path else [])]
    context = load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="rating-legalita",
        input_paths=paths,
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise ValueError("Portable Rating context v2 required")
    client = case["client"]
    if client is not None and (
        client["archive_client_id"] != context["client_id"]
        or client["engagement_id"] != context["engagement_id"]
    ):
        raise ValueError("Rating case belongs to another client or engagement")
    source_root = Path(context["run_root"]) / "inputs"
    load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="rating-legalita",
        input_paths=[
            rating_case.evidence_path(source_root, row["uri"])
            for row in case["evidence"]
        ],
    )
    # Public prerequisite, quote, history and decision checks precede projection.
    record = rating_case.assess_case(case, source_root, previous)
    report = rating_case.render_dossier(record)
    output = Path(context["output_dir"])
    if request["operation"] == "render":
        sys.argv = [
            "rating_case.py",
            "render",
            "--case",
            str(case_path),
            "--source-root",
            str(source_root),
            "--output",
            str(output),
            "--client-engagement",
            request["context"],
            *(["--previous", str(previous_path)] if previous_path else []),
        ]
        if rating_case.main() != 0:
            raise ValueError("Rating render refused")
    if request["operation"] in {"render", "replay"}:
        directory = output / record["record_sha256"]
        expected = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        if (directory / "dossier.json").read_text(encoding="utf-8") != expected or (
            directory / "dossier.md"
        ).read_text(encoding="utf-8") != report:
            raise ValueError("Rating artifacts differ from unchanged public replay")
    elif request["operation"] != "inspect":
        raise ValueError("Unknown Rating operation")
    sys.stdout.write(
        json.dumps(
            {"record": record, "report": report}, ensure_ascii=False, allow_nan=False
        )
    )


if __name__ == "__main__":
    main()
