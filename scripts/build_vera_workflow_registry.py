"""Generate factual Vera component metadata without making routing decisions."""

from __future__ import annotations

import argparse
import ast
import json
import logging
from pathlib import Path
from typing import Any

__all__ = ["build_registry", "main"]

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("plugins/vera/skills/vera/references/workflow-registry.json")


def build_registry(root: Path) -> dict[str, Any]:
    """Derive component membership, skill paths and executable scripts from source."""

    components = json.loads((root / "plugins/vera/components.json").read_text())[
        "plugins"
    ]
    if len(components) != len(set(components)):
        raise ValueError("Vera component IDs must be unique")
    records = []
    for component in components:
        directory = root / "plugins" / component
        if not directory.is_dir() or directory.parent != root / "plugins":
            raise ValueError(f"Invalid Vera component: {component}")
        skills = [
            f"modules/{component}/{path.relative_to(directory).as_posix()}"
            for path in sorted((directory / "skills").glob("*/SKILL.md"))
        ]
        if not skills:
            raise ValueError(f"Vera component has no skill: {component}")
        entrypoints = []
        for path in sorted((directory / "scripts").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
                and any(
                    isinstance(value, ast.Constant) and value.value == "__main__"
                    for value in node.test.comparators
                )
                for node in tree.body
            ):
                entrypoints.append(f"modules/{component}/scripts/{path.name}")
        records.append(
            {
                "component_id": component,
                "skills": skills,
                "python_entrypoints": entrypoints,
            }
        )
    return {
        "schema_version": 1,
        "membership_source": "components.json",
        "routing_policy": "Use the semantic workflow catalog and selected skill; entrypoint presence is not workflow suitability or host qualification.",
        "managed_run_required_artifacts": [
            "model_data_report.json",
            "model_data_report.md",
        ],
        "host_qualification": {
            "native_semantic_worker": {
                "components": ["journal-bank-reconciliation", "passive-invoice-audit"],
                "diagnostic": "modules/journal-bank-reconciliation/scripts/semantic_review.py host-status",
                "requirement": "Exact qualified native capsule and launch-time canaries; inspect current host before promising execution.",
            },
            "browser_automation": {
                "component": "browser-automation",
                "requirement": "Connected Chrome with the documented Playwright tab API; native steps and unobservable downloads remain explicit gaps.",
            },
        },
        "components": records,
        "vera_wrapper_skills": [
            path.relative_to(root / "plugins/vera").as_posix()
            for path in sorted((root / "plugins/vera/skills").glob("*/SKILL.md"))
        ],
    }


def main() -> int:
    """Write the registry, or fail when checked metadata differs from source."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = json.dumps(build_registry(ROOT), ensure_ascii=False, indent=2) + "\n"
    target = ROOT / REGISTRY
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != expected:
            logging.error(
                "Vera workflow registry is stale; regenerate from canonical source."
            )
            return 1
    else:
        target.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
