"""Run or review a treasury forecast inside a bound Studio Archive engagement."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (candidate / "vera_assurance").is_dir():
        sys.path.insert(0, str(candidate))
        break

from treasury_core import TreasuryError  # noqa: E402
from treasury_inputs import (  # noqa: E402
    load_inputs,
    manifest_paths,
    read_json,
    write_templates,
)
from treasury_session import (  # noqa: E402
    create_session,
    current_record,
    review_session,
    save_scenario,
)
from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

__all__ = ["main", "validate_context"]


def validate_context(context_path: Path, paths: list[Path] | None = None) -> dict:
    """Require a current running portable archive context on every review action."""
    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id="treasury-forecast",
        input_paths=paths or [],
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise TreasuryError("Treasury requires a portable v2 client workflow")
    return context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    templates = sub.add_parser(
        "templates", help="Create empty documented CSV templates"
    )
    templates.add_argument("--output", type=Path, required=True)
    prepare = sub.add_parser(
        "prepare", help="Import the fixed tables and create a reviewable draft"
    )
    prepare.add_argument("--manifest", type=Path, required=True)
    for name in ("review", "serve", "context", "scenario"):
        command = sub.add_parser(name)
        if name in {"review", "scenario"}:
            command.add_argument("--request", type=Path, required=True)
        if name == "context":
            command.add_argument("--event-id", action="append", default=[])
        if name == "serve":
            command.add_argument("--port", type=int, default=0)
    for name, command in sub.choices.items():
        if name != "templates":
            command.add_argument("--client-engagement", type=Path, required=True)
    args = parser.parse_args(argv)
    context = None
    try:
        if args.command == "templates":
            write_templates(args.output)
            return 0
        paths = [args.manifest] if args.command == "prepare" else []
        context = validate_context(args.client_engagement, paths)
        output = Path(context["output_dir"])
        if args.command == "prepare":
            manifest = read_json(args.manifest)
            input_root = Path(context["run_root"]) / "inputs"
            sources = [args.manifest, *manifest_paths(manifest, input_root)]
            context = validate_context(args.client_engagement, sources)
            data, previous = load_inputs(
                manifest,
                input_root,
                client_id=context["client_id"],
                engagement_id=context["engagement_id"],
            )
            record = create_session(
                output,
                data,
                previous,
                source_paths=sources,
                context_path=args.client_engagement,
            )
        else:
            state, record = current_record(output)
            source_paths = [Path(row["path"]) for row in state["sources"]]
            validate_context(args.client_engagement, source_paths)
            if args.command == "serve":
                from treasury_server import serve

                serve(
                    output,
                    validate=lambda: validate_context(
                        args.client_engagement, source_paths
                    ),
                    port=args.port,
                )
                return 0
            if args.command == "review":
                request = read_json(args.request)
                record = review_session(
                    output,
                    expected_record_sha256=request["record_sha256"],
                    decisions=request.get("decisions"),
                    review=request.get("review"),
                )
            elif args.command == "context":
                selected = set(args.event_id)
                if len(selected) > 100 or selected - {
                    row["event_id"] for row in record["events"]
                }:
                    raise TreasuryError("Select at most 100 existing event IDs")
                logging.info(
                    "%s",
                    json.dumps(
                        {
                            "record_sha256": record["record_sha256"],
                            "events": [
                                row
                                for row in record["events"]
                                if row["event_id"] in selected
                            ],
                        },
                        ensure_ascii=False,
                    ),
                )
                return 0
            elif args.command == "scenario":
                save_scenario(
                    output,
                    expected_record_sha256=record["record_sha256"],
                    dates=read_json(args.request),
                )
                logging.info("Alternative saved in %s", output)
                return 0
        logging.info(
            "Treasury %s; record %s; outputs %s",
            record["status"],
            record["record_sha256"],
            output,
        )
        return 0
    except (
        TreasuryError,
        AssuranceContractError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        logging.error("Treasury blocked: %s", exc)
        if context is not None:
            output = Path(context["output_dir"])
            output.mkdir(parents=True, exist_ok=True)
            (output / "treasury_blocked.json").write_text(
                json.dumps(
                    {
                        "workflow_id": "treasury-forecast",
                        "status": "blocked",
                        "reason": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
