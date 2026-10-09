"""Isolated maintained input inspection and mechanical case contracts, no runner."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Inspect or validate without selecting semantic roles or calculating outputs."""
    root = Path(sys.argv[1])
    request = json.loads(sys.stdin.read(2_000_001))
    sys.path.insert(0, str(root / "scripts"))
    for vendor in (root / "vendor/modules", root.parent / "_shared/vendor/modules"):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    import management_control_core as core
    from vera_assurance import load_client_engagement_context_file

    sources = [Path(p) for p in request["sources"]]
    context = load_client_engagement_context_file(
        Path(request["context"]),
        expected_workflow_id="management-control-pack",
        input_paths=sources,
    )
    operation, mode = request["operation"], request["mode"]
    if operation == "inspect":
        output = Path(request["output"])
        if mode == "reporting":
            import inspect_inputs

            arguments = [part for path in sources for part in ("--input", str(path))]
            with contextlib.redirect_stdout(io.StringIO()):
                code = inspect_inputs.main(
                    [
                        *arguments,
                        "--client-engagement",
                        request["context"],
                        "--output-dir",
                        str(output),
                    ]
                )
            if code:
                raise ValueError("Public Management input inspection refused")
        else:
            output.mkdir(exist_ok=False)
            core.write_json(
                output / "source_receipts.json",
                {
                    "schema_version": "vera.native.management_costing_sources.v1",
                    "sources": [
                        {
                            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                            "byte_count": p.stat().st_size,
                        }
                        for p in sources
                    ],
                    "boundary": "Explicit selected sources; no ledger requirement, inferred source roles, source extraction, costing amounts or methods.",
                },
            )
        result = {"inspected": True, "mode": mode, "calculated": False}
    else:
        case = request["case"]
        if mode == "reporting":
            tables = core.load_source_tables(sources)
            inspection, _, _ = core.build_inspection(tables)
            if (
                case.get("schema_version") != core.RECIPE_SCHEMA
                or case.get("workflow_id") != core.WORKFLOW_ID
                or case.get("inventory_sha256") != inspection["inventory_sha256"]
            ):
                raise ValueError(
                    "Reporting proposal must identify this exact public inventory"
                )
            if operation == "stage" and case.get("mapping_review") != {
                "status": "not_reviewed",
                "reviewer": "",
                "reviewed_at": "",
            }:
                raise ValueError(
                    "New reporting mappings must retain an empty pending human review"
                )
            if not isinstance(case.get("tables"), dict):
                raise ValueError("Keep the complete literal public table mappings")
            table_map = {table.table_id: table for table in tables}
            for role in case["tables"]:
                core._recipe_table(case, table_map, role)
            if operation == "register":
                # The declared named readback already exists; do not fabricate a preview reviewer.
                core._review_recipe(case, inspection["inventory_sha256"])
            result = {
                "identity_verified": True,
                "inventory_sha256": inspection["inventory_sha256"],
                "calculated": False,
                "semantic_review": False,
            }
        else:
            import costing_core

            if case.get("schema_version") != "vera.costing_case.v1":
                raise ValueError("Use the entire ordinary costing payload")
            costing_core._validate(case["case"], case["methods"])
            meta = case["case"]["meta"]
            if (
                meta["clientId"] != context["client_id"]
                or meta["engagementId"] != context["engagement_id"]
            ):
                raise PermissionError(
                    "Costing case belongs to another client or engagement"
                )
            hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
            if len(hashes) != len(sources) or any(
                row.get("source_sha256") not in hashes
                for row in case["case"]["evidence"]
            ):
                raise ValueError(
                    "Every costing evidence must identify an exact distinct selected source"
                )
            if (
                not isinstance(case.get("entity"), str)
                or not case["entity"].strip()
                or not isinstance(case.get("decision_question"), str)
                or not case["decision_question"].strip()
            ):
                raise ValueError(
                    "Retain the complete costing entity and decision question"
                )
            result = {
                "identity_verified": True,
                "selected_source_hashes_verified": True,
                "calculated": False,
                "semantic_review": False,
            }
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
