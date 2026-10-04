"""Local stdlib bridge for native course chat controls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _desktop_teaching import PLUGIN_ROOT
from courseware.access import CourseAccessError
from courseware.chat import CourseChats

__all__ = ["main"]


def main() -> int:
    """Return a bounded UI invitation or a validated worker assignment."""
    try:
        request = json.load(sys.stdin)
        args = request["arguments"]
        chats = CourseChats(Path(args["state_root"]), PLUGIN_ROOT)
        if request["operation"] not in {"prepare", "claim"}:
            raise ValueError("Unknown course chat operation")
        result = (
            chats.prepare(args)
            if request["operation"] == "prepare"
            else chats.claim(args["invitation"], args["thread_id"])
        )
        sys.stdout.write(json.dumps(result) + "\n")
        return 0
    except CourseAccessError as exc:
        sys.stdout.write(json.dumps(exc.as_dict()) + "\n")
        return 2
    except (ValueError, OSError, KeyError) as exc:
        sys.stdout.write(json.dumps({"status": "blocked", "error": str(exc)}) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
