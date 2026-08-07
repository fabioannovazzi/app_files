"""Record one reviewed source relationship without assigning legal priority."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from case_core import (
    case_lock,
    iso_now,
    load_running_context,
    require_run_artifact,
    safe_identifier,
    write_private_json,
)

__all__ = ["link_sources", "main"]

LOGGER = logging.getLogger(__name__)
RELATIONSHIP_KINDS = {
    "amends",
    "supersedes",
    "clarifies",
    "implements",
    "incorporated_by",
}


def link_sources(
    *,
    output_dir: Path,
    client_engagement: Path,
    source_id: str,
    kind: str,
    target_source_id: str,
) -> dict[str, Any]:
    """Add one idempotent relationship between two different registered sources."""

    source_id = safe_identifier(source_id, field="source_id")
    target_source_id = safe_identifier(target_source_id, field="target_source_id")
    if kind not in RELATIONSHIP_KINDS:
        raise ValueError(f"unsupported relationship kind: {kind}")
    if source_id == target_source_id:
        raise ValueError("a source cannot relate to itself")
    context = load_running_context(client_engagement, output_dir=output_dir)
    run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    relationship = {"kind": kind, "target_source_id": target_source_id}
    with case_lock(output_dir):
        register_path = output_dir / "source_register.json"
        register = require_run_artifact(register_path, run_id=run_id)
        sources = register.get("sources")
        if not isinstance(sources, list):
            raise ValueError("source_register.json has invalid sources")
        by_id = {
            str(item.get("source_id")): item
            for item in sources
            if isinstance(item, dict)
        }
        if source_id not in by_id or target_source_id not in by_id:
            raise ValueError("both relationship sources must already be registered")
        relationships = by_id[source_id].get("relationships")
        if not isinstance(relationships, list):
            raise ValueError("source relationships must be a list")
        if relationship in relationships:
            return relationship
        if any(
            isinstance(item, dict)
            and item.get("target_source_id") == target_source_id
            and item.get("kind") != kind
            for item in relationships
        ):
            raise ValueError(
                "the same source pair already has a different relationship; "
                "professional review must resolve it first"
            )
        relationships.append(relationship)
        register["source_set_revision"] = int(register["source_set_revision"]) + 1
        write_private_json(register_path, register)
        run_state_path = output_dir / "run_state.json"
        run_state = require_run_artifact(run_state_path, run_id=run_id)
        run_state.update(
            {
                "updated_at": iso_now(),
                "phase": "source_baseline_review",
                "status": "needs_review",
                "source_set_revision": register["source_set_revision"],
            }
        )
        write_private_json(run_state_path, run_state)
    return relationship


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--kind", required=True, choices=sorted(RELATIONSHIP_KINDS))
    parser.add_argument("--target-source-id", required=True)
    args = parser.parse_args(argv)
    relationship = link_sources(
        output_dir=args.output_dir,
        client_engagement=args.client_engagement,
        source_id=args.source_id,
        kind=args.kind,
        target_source_id=args.target_source_id,
    )
    LOGGER.info(
        "Recorded %s relationship to %s",
        relationship["kind"],
        relationship["target_source_id"],
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
