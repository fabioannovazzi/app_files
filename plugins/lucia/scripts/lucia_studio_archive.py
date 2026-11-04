"""Run Lucia's supported Studio Archive operations through the shared CLI."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

__all__ = ["main"]

_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Validate the Lucia operation before delegating to the maintained Archive."""
    args = sys.argv[1:] if argv is None else argv
    component = _ROOT / "modules/studio-archive"
    if not component.is_dir():
        component = _ROOT.parent / "studio-archive"
    sys.path.insert(0, str(component / "scripts"))
    import studio_archive

    os.environ["LUCIA_ASSURANCE_HOST"] = "1"
    workflows = json.loads((_ROOT / "components.json").read_text(encoding="utf-8"))[
        "workflow_roles"
    ]["studio-archive"]["supports"]
    excluded = {"start-check-entries-from-sample", "verify-run-report"}
    # Use the shared parser so help, aliases and repeated flags resolve exactly
    # as they do in the worker. Strip inapplicable commands before parsing.
    parser = studio_archive._parser()
    commands = next(
        action.choices for action in parser._actions if action.dest == "command"
    )
    for command in excluded:
        del commands[command]
    prepare = commands["prepare-workflow"]
    workflow_id = next(
        action for action in prepare._actions if action.dest == "workflow_id"
    )
    workflow_id.choices = workflows
    parser.description = __doc__
    parser.parse_args(args)
    return studio_archive.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
