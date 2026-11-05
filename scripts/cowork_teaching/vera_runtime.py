"""Vera's written lessons report completion separately from kit preparation."""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from course_completion import finish_written
from written_course_materials import main as prepare_materials

__all__ = ["main"]


def main() -> int:
    """Delegate shared preparation and bind Vera's introductory or specialist course."""
    if sys.argv[1:2] == ["finish"]:
        parser = argparse.ArgumentParser(description="Finish the reviewed Vera lesson")
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--demo-output", type=Path, required=True)
        parser.add_argument("--practice-output", type=Path, required=True)
        parser.add_argument("--confirmed-understanding", action="store_true")
        args = parser.parse_args(sys.argv[2:])
        try:
            result = finish_written(
                args.output_dir,
                args.demo_output,
                args.practice_output,
                args.confirmed_understanding,
            )
        except (OSError, ValueError) as error:
            parser.exit(2, str(error) + "\n")
        sys.stdout.write(json.dumps(result) + "\n")
        return 0
    if sys.argv[1:2] == ["prepare"] and "--introduction" in sys.argv[2:]:
        sys.argv.remove("--introduction")
        output = io.StringIO()
        with redirect_stdout(output):
            code = prepare_materials()
        if code:
            sys.stdout.write(output.getvalue())
            return code
        result = json.loads(output.getvalue())
        result["course_id"] = "get-started"
        provenance = Path(result["course"]).with_name("course-provenance.json")
        tmp = provenance.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(provenance)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    return prepare_materials()


if __name__ == "__main__":
    raise SystemExit(main())
