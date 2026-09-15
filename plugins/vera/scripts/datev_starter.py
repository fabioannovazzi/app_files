#!/usr/bin/env python3
"""Persist a DATEV native starter using existing progress and review contracts.

This is a local recorder, not a desktop executor. Fixed shape, path, revision
and provenance checks provide auditability; professional judgment stays model-led.
No network client, UI framework or package installation is used here.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import logging
import platform
import re
import sys
from pathlib import Path
from typing import Any

__all__ = ["start", "resume", "record", "save_client_review", "prepare", "main"]
ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules/browser-automation"
if not MODULE.is_dir():
    MODULE = ROOT.parent / "browser-automation"
sys.path.insert(0, str(MODULE / "scripts"))
checkpoint = importlib.import_module("teaching_checkpoint")
batch = importlib.import_module("batch_review")
development = importlib.import_module("development_request")
LOG = logging.getLogger(__name__)
PROCEDURE = MODULE / "references/passive-invoice-procedure.md"
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
OBJECTIVE = "Adattare la procedura nota delle fatture passive a DATEV nativo Windows"


def _private(directory: Path) -> None:
    """Reject links and Git output; the operator selects a private local parent."""
    if not directory.is_absolute() or any(
        p.is_symlink() or (p / ".git").exists() for p in (directory, *directory.parents)
    ):
        raise ValueError("Use an absolute private path outside Git without symlinks")


def _native_checkpoint(directory: Path) -> dict[str, Any]:
    """Require this route's exact saved identity before reusing a progress chain."""
    record = checkpoint.read_checkpoint(directory)
    if record["payload"]["objective"] != OBJECTIVE:
        raise ValueError("This is not a DATEV starter checkpoint")
    return record


def start(directory: Path) -> dict[str, Any]:
    """Create initial progress with the shipped procedure, never a fake example."""
    _private(directory)
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    procedure = PROCEDURE.read_text(encoding="utf-8")
    payload = {
        "schema_version": checkpoint.SCHEMA,
        "objective": OBJECTIVE,
        "start_state": (
            f"Vera {manifest['version']}; host Python {platform.system()}. "
            "Prodotto/versione DATEV e controllo nativo ancora da verificare. "
            "Nessun profilo o dato del precedente tester importato."
        ),
        "end_condition": "Un esempio reale revisionabile, con provenienza ed esito espliciti, oppure un gap preciso salvato",
        "status": "paused",
        "resume_instruction": "Verificare prodotto/versione DATEV, desktop Windows attivo e API native effettivamente disponibili; poi un solo cliente e una fattura",
        "steps": [],
    }
    checkpoint.save_checkpoint(directory, payload, expected_revision=0)
    # The procedure is public authored material, not a customer observation.
    with (directory / "PROCEDURA.md").open("x", encoding="utf-8") as stream:
        stream.write(procedure)
    return resume(directory)


def resume(directory: Path) -> dict[str, Any]:
    """Recover the existing chain and report, including after interrupted output."""
    _private(directory)
    _native_checkpoint(directory)
    summary = checkpoint.summarize_checkpoint(directory)
    summary["report_path"] = str(checkpoint.write_progress_report(directory))
    summary["route"] = "datev-native-guided"
    summary["native_replay_validated"] = False
    summary["client_reviews"] = []
    for path in sorted(directory.glob("client-*")):
        _private(path)
        if path.is_dir():
            summary["client_reviews"].append(str(batch.render_review(path)))
    return summary


def record(
    directory: Path, event: dict[str, Any], *, expected_revision: int
) -> dict[str, Any]:
    """Append attributed evidence without forging browser observation receipts."""
    _private(directory)
    required = checkpoint.STEP_TEXT | {
        "source_type",
        "source_ref",
        "uncertainties",
        "next_step",
    }
    if (
        not isinstance(event, dict)
        or set(event) != required
        or event["source_type"]
        not in {
            "host_tool",
            "operator_report",
            "reference",
            "unknown",
        }
    ):
        raise ValueError("Use an attributed native event, not browser capture fields")
    if not all(
        isinstance(event[k], str) and 0 < len(event[k].strip()) <= 1500
        for k in (*checkpoint.STEP_TEXT, "source_ref", "next_step")
    ):
        raise ValueError("A bounded source reference and exact next step are required")
    old = _native_checkpoint(directory)
    if old["revision"] != expected_revision:
        raise ValueError("Stale DATEV progress; resume before saving")
    payload = copy.deepcopy(old["payload"])
    step = {k: event[k] for k in checkpoint.STEP_TEXT}
    # Native tool reports retain their real source. The legacy transport label
    # is not a claim of operator testimony or a browser observation receipt.
    step["outcome"] = (
        f"[{event['source_type']}: {event['source_ref']}] {event['outcome']}"
    )
    step["evidence_basis"] = (
        "unknown" if event["source_type"] == "unknown" else "operator_report"
    )
    step["capture"] = None
    step["uncertainties"] = event["uncertainties"]
    step["status"] = "unresolved" if event["uncertainties"] else "understood"
    payload["steps"].append(step)
    payload["status"] = "paused"
    payload["resume_instruction"] = event["next_step"]
    checkpoint.save_checkpoint(directory, payload, expected_revision=expected_revision)
    return resume(directory)


def save_client_review(
    directory: Path, client_key: str, payload: dict[str, Any], *, expected_revision: int
) -> str:
    """Persist one real client's full snapshot with the existing correction rules."""
    _private(directory)
    _native_checkpoint(directory)
    if not SLUG.fullmatch(client_key):
        raise ValueError("Use a local client key without path components")
    target = directory / f"client-{client_key}"
    _private(target)
    if expected_revision:
        old = batch.read_review(target)["payload"]
        if any(old[k] != payload[k] for k in ("batch_id", "scope")):
            raise ValueError("A client review cannot change its identity or scope")
    return str(batch.save_review(target, payload, expected_revision=expected_revision))


def prepare(directory: Path, payload: dict[str, Any], output: Path) -> dict[str, Any]:
    """Freeze agent-selected sanitized text for review; never submit or copy cases."""
    _private(directory)
    _private(output)
    _native_checkpoint(directory)
    return development.prepare_request(payload, output, checkpoint=directory)


def main(argv: list[str] | None = None) -> int:
    """Run local commands; the agent prepares input files, never the accountant."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("start", "resume", "record", "save-review", "prepare-request"),
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--client-key")
    parser.add_argument("--expected-revision", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            result = start(args.directory)
        elif args.command == "resume":
            result = resume(args.directory)
        else:
            if args.input is None:
                parser.error("This command requires --input")
            payload = json.loads(args.input.read_text(encoding="utf-8"))
            if args.command == "prepare-request":
                if args.output is None:
                    parser.error("prepare-request requires --output")
                result = prepare(args.directory, payload, args.output)
            else:
                if args.expected_revision is None:
                    parser.error("An exact --expected-revision is required")
                if args.command == "record":
                    result = record(
                        args.directory,
                        payload,
                        expected_revision=args.expected_revision,
                    )
                else:
                    if not args.client_key:
                        parser.error("save-review requires --client-key")
                    result = {
                        "review_path": save_client_review(
                            args.directory,
                            args.client_key,
                            payload,
                            expected_revision=args.expected_revision,
                        )
                    }
        LOG.info("%s", json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        LOG.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
