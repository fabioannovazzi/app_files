"""Distribute one reporting implementation to each standalone product package."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

__all__ = ["synchronize", "reporting_tool_schemas", "main"]
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("vera", "clara", "lucia")
LOGGER = logging.getLogger(__name__)


def reporting_tool_schemas() -> bytes:
    """Project server schemas into local tools without credential arguments."""
    from modules.operational_incidents.api import TOOLS

    def references(value: Any) -> set[str]:
        if isinstance(value, dict):
            found = (
                {value["$ref"].removeprefix("#/$defs/")} if "$ref" in value else set()
            )
            return found.union(*(references(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(references(item) for item in value))
        return set()

    result = []
    for source in TOOLS:
        if source["name"] in {"vera_workflow_record", "vera_workflow_status"}:
            continue  # The native workflow_usage tool owns these durable operations.
        tool = json.loads(json.dumps(source))
        if tool["name"] == "vera_incident_register":
            tool["description"] = (
                "Register or inspect this installed product's retained local reporting identity "
                "through ordinary HTTPS. Pass no arguments. Private credentials stay in the "
                "reporter; this does not claim a browser-owned task."
            )
        elif tool["name"] == "vera_workflow_stamp":
            tool["description"] = (
                "Stamp the exact retained model_data_receipt_request.json through ordinary HTTPS "
                "for a run owned by this local reporter. Supply its original run_id and "
                "receipt_request, never report contents, paths or credentials. Save the exact "
                "returned receipt beside the request, then use workflow_usage.py stamp-report "
                "and deliver its queued receipt event. Stamping does not link the receipt or "
                "prove task completion. Browser-owned runs use the browser workflow-stamp operation."
            )
        schema = tool["inputSchema"]
        definitions = schema.pop("$defs", {})
        for field in ("credentials", "client_status"):
            schema["properties"].pop(field, None)
        required = references(schema)
        pending = set(required)
        while pending:
            name = pending.pop()
            added = references(definitions[name]) - required
            required.update(added)
            pending.update(added)
        if required:
            schema["$defs"] = {name: definitions[name] for name in sorted(required)}
        result.append(tool)
    return (json.dumps(result, indent=2) + "\n").encode()


def synchronize(root: Path = ROOT, *, check: bool = False) -> list[str]:
    """Compare exact source bytes; packaging may never silently fork this runtime."""
    differences = []
    for source in sorted((root / "plugins/_shared/reporting-runtime").iterdir()):
        if source.suffix not in {".py", ".cjs", ".json"}:
            continue
        content = source.read_bytes()
        for product in PRODUCTS:
            target = root / "plugins" / product / "scripts" / source.name
            if not target.is_file() or target.read_bytes() != content:
                differences.append(str(target.relative_to(root)))
                if not check:
                    target.write_bytes(content)
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--refresh-schemas",
        action="store_true",
        help="Regenerate the reviewed local tool schemas using the server development dependencies.",
    )
    args = parser.parse_args()
    if args.refresh_schemas:
        if args.check:
            parser.error("--refresh-schemas cannot be combined with --check")
        schema_path = (
            ROOT / "plugins/_shared/reporting-runtime/incident_tool_schemas.json"
        )
        schema_path.write_bytes(reporting_tool_schemas())
    differences = synchronize(check=args.check)
    if args.check and differences:
        LOGGER.error("Shared reporting source drift: %s", ", ".join(differences))
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
