"""Usage: python -m patent_box.cli --help"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .contracts import ContractError, read_json, validate
from .engine import calculate
from .monitor import compare_snapshots, impact_queue
from .render import markdown, reconciliation_csv

__all__ = ["write_new", "dump", "main"]


def write_new(path: str | Path, content: str) -> None:
    with Path(path).open("x", encoding="utf-8", newline="") as handle:
        handle.write(content)


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Patent Box developer reference: no live Vera integration"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("input")
    check.add_argument(
        "--schema",
        required=True,
        choices=["case", "ruleset", "source-snapshot", "case-index"],
    )
    run = sub.add_parser("calculate")
    run.add_argument("case")
    run.add_argument("--rules", required=True)
    run.add_argument("--evidence-root", required=True)
    run.add_argument(
        "--as-of",
        required=True,
        help="Explicit YYYY-MM-DD; never hidden current-date assumptions",
    )
    run.add_argument(
        "--output", required=True, help="New, nonexistent output directory"
    )
    monitor = sub.add_parser("source-diff")
    monitor.add_argument("before")
    monitor.add_argument("after")
    monitor.add_argument("--case-index", required=True)
    monitor.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate(read_json(args.input), f"{args.schema}.schema.json")
            print(
                dump(
                    {"status": "VALID_SHAPE_ONLY", "semantic_review": "NOT_PERFORMED"}
                ),
                end="",
            )
            return 0
        if args.command == "calculate":
            result = calculate(
                read_json(args.case),
                read_json(args.rules),
                evidence_root=args.evidence_root,
                as_of=args.as_of,
            )
            out = Path(args.output)
            out.mkdir(parents=True, exist_ok=False)
            write_new(out / "result.json", dump(result))
            write_new(out / "workpaper.md", markdown(result))
            write_new(out / "cost_reconciliation.csv", reconciliation_csv(result))
            print(
                dump(
                    {
                        "status": result["status"],
                        "output": str(out),
                        "additional_deduction": result["additional_deduction"],
                    }
                ),
                end="",
            )
            return 0
        comparison = compare_snapshots(read_json(args.before), read_json(args.after))
        queue = impact_queue(comparison, read_json(args.case_index))
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=False)
        write_new(out / "source_changes.json", dump(comparison))
        write_new(out / "impact_queue.json", dump(queue))
        print(
            dump(
                {
                    "status": comparison["status"],
                    "events": len(comparison["events"]),
                    "review_items": len(queue["items"]),
                }
            ),
            end="",
        )
        return 0
    except (ContractError, ValueError, OSError, KeyError) as exc:
        print(dump({"status": "BLOCKED", "error": str(exc)}), file=sys.stderr, end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
