"""Prepare written Cowork lessons from this installation's reviewed catalogue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["main"]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "vendor/modules"))
from courseware.library import CourseLibrary  # noqa: E402


def main() -> int:
    """List or prepare a kit without executing a workflow or recording completion."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("workflow")
    prepare.add_argument("--language", required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    eligible = {
        path.parent.name for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")
    }
    library = CourseLibrary(PLUGIN_ROOT, eligible)
    if args.command == "list":
        print(json.dumps(library.catalog(), ensure_ascii=False, indent=2))
        return 0
    destination = args.output_dir.expanduser().absolute()
    if destination.resolve().is_relative_to(PLUGIN_ROOT.resolve()):
        raise ValueError("Choose a lesson folder outside the installed plugin")
    result = library.render(args.workflow, args.language, destination)
    # Native session handoffs do not apply to a written single-conversation lesson.
    (destination / "execution-request.json").unlink(missing_ok=True)
    result.pop("execution_request", None)
    result["mode"] = "cowork-written-single-conversation"
    result["prepared_artifacts"] = [
        item
        for item in result["prepared_artifacts"]
        if Path(item["path"]).name != "execution-request.json"
    ]
    (destination / "course-provenance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "lesson-progress.md").write_text(
        f"# {library.product}: {args.workflow}\n\nLanguage: {args.language}\n\n"
        "Status: prepared, not executed.\n\n"
        "Demonstration: not started.\nPractice: not started.\n"
        "Understanding: not confirmed.\n\n"
        "Next step: inspect the fictional inputs and explain the requested result.\n",
        encoding="utf-8",
    )
    # Suppresses tutorial receipt transport when a normal workflow helper is reused.
    (destination / ".vera-onboarding-local-only").touch()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
