#!/usr/bin/env python3
"""Persist model-authored teaching progress without raw browser capture.

Shape, revision order and hashes are mechanical checks. The current model owns
the meaning of each step and whether its evidence supports that interpretation.
A checkpoint is never an execution receipt or an approved developer pack.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from capability_pipeline import canonical_json_bytes, sha256_payload

__all__ = ["read_checkpoint", "save_checkpoint", "validate_checkpoint", "main"]

LOGGER = logging.getLogger(__name__)
SCHEMA = "browser-teaching-checkpoint/v1"
TEXT_FIELDS = {"objective", "start_state", "end_condition", "resume_instruction"}
STEP_TEXT = {"id", "intent", "action", "decision_reason", "outcome", "postcondition"}
STEP_KEYS = STEP_TEXT | {"status", "evidence_basis", "uncertainties", "capture"}
CAPTURE_KEYS = {
    "started_at",
    "ended_at",
    "stop_reason",
    "transition_count",
    "before_sha256",
    "after_sha256",
}
HEX = re.compile(r"[a-f0-9]{64}")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2000


def validate_checkpoint(payload: Any) -> None:
    """Check explicit shape and evidence declarations, never infer page meaning."""
    if not isinstance(payload, dict) or set(payload) != TEXT_FIELDS | {
        "schema_version",
        "status",
        "steps",
    }:
        raise ValueError("checkpoint fields do not match the teaching contract")
    if payload["schema_version"] != SCHEMA:
        raise ValueError("unsupported teaching checkpoint schema")
    if not all(_text(payload[key]) for key in TEXT_FIELDS):
        raise ValueError(
            "objective, boundaries and exact resume instruction are required"
        )
    if payload["status"] not in {"paused", "needs_clarification", "ready_for_review"}:
        raise ValueError("checkpoint cannot claim execution or transfer approval")
    steps = payload["steps"]
    if not isinstance(steps, list) or len(steps) > 100:
        raise ValueError("steps must be an array of at most 100 steps")
    ids = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != STEP_KEYS:
            raise ValueError("step fields do not match the teaching contract")
        if not all(_text(step[key]) for key in STEP_TEXT):
            raise ValueError(
                "each step needs intent, action, reason, outcome and postcondition"
            )
        if step["id"] in ids:
            raise ValueError("step ids must be unique")
        ids.add(step["id"])
        if step["status"] not in {"understood", "unresolved"}:
            raise ValueError("step must be understood or unresolved")
        if step["evidence_basis"] not in {"observed", "operator_report", "unknown"}:
            raise ValueError("step must distinguish observations from operator reports")
        questions = step["uncertainties"]
        if not isinstance(questions, list) or not all(_text(q) for q in questions):
            raise ValueError("uncertainties must be an array of specific questions")
        if step["status"] == "understood" and (
            questions or step["evidence_basis"] == "unknown"
        ):
            raise ValueError("unresolved evidence cannot be marked understood")
        if step["status"] == "unresolved" and not questions:
            raise ValueError("an unresolved step needs a concrete question")
        capture = step["capture"]
        if capture is not None:
            if not isinstance(capture, dict) or set(capture) != CAPTURE_KEYS:
                raise ValueError("only bounded capture summaries may be saved")
            if capture["stop_reason"] not in {
                "time_limit",
                "transition_limit",
                "operator_pause",
            }:
                raise ValueError("capture needs an explicit observation stop reason")
            if not all(_text(capture[k]) for k in ("started_at", "ended_at")):
                raise ValueError("capture needs observation timestamps")
            count = capture["transition_count"]
            if type(count) is not int or not 0 <= count <= 100:
                raise ValueError("invalid transition count")
            if not all(
                isinstance(capture[k], str) and HEX.fullmatch(capture[k])
                for k in ("before_sha256", "after_sha256")
            ):
                raise ValueError("capture state hashes are required")
        if step["evidence_basis"] == "observed" and capture is None:
            raise ValueError("observed steps require a capture summary")
    if payload["status"] == "ready_for_review" and (
        not steps
        or any(step["status"] != "understood" for step in steps)
        or steps[-1]["evidence_basis"] != "observed"
    ):
        raise ValueError("review needs understood steps and an observed final outcome")


def read_checkpoint(directory: Path) -> dict[str, Any]:
    """Read the latest immutable revision and verify its complete hash chain."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("checkpoint directory must be a real directory")
    paths = sorted(directory.glob("checkpoint-*.json"))
    previous = None
    latest: dict[str, Any] = {}
    for revision, path in enumerate(paths, 1):
        if path.is_symlink() or path.name != f"checkpoint-{revision:04d}.json":
            raise ValueError("checkpoint revision sequence is invalid")
        record = json.loads(path.read_text(encoding="utf-8"))
        if set(record) != {"revision", "previous_sha256", "payload", "sha256"}:
            raise ValueError("invalid checkpoint record")
        unsigned = {k: v for k, v in record.items() if k != "sha256"}
        if (
            record["revision"] != revision
            or record["previous_sha256"] != previous
            or record["sha256"] != sha256_payload(unsigned)
        ):
            raise ValueError("checkpoint hash chain is invalid")
        validate_checkpoint(record["payload"])
        previous = record["sha256"]
        latest = record
    if not latest:
        raise ValueError("no teaching checkpoint found")
    return latest


def save_checkpoint(
    directory: Path, payload: dict[str, Any], *, expected_revision: int
) -> Path:
    """Append without overwriting prior progress or changing existing permissions."""
    validate_checkpoint(payload)
    if type(expected_revision) is not int or not 0 <= expected_revision < 9999:
        raise ValueError("invalid expected revision")
    previous = None
    if expected_revision == 0:
        directory.mkdir(mode=0o700)
    else:
        latest = read_checkpoint(directory)
        if latest["revision"] != expected_revision:
            raise ValueError("stale teaching checkpoint; resume the latest revision")
        previous = latest["sha256"]
    record = {
        "revision": expected_revision + 1,
        "previous_sha256": previous,
        "payload": payload,
    }
    record["sha256"] = sha256_payload(record)
    path = directory / f"checkpoint-{expected_revision + 1:04d}.json"
    # Exclusive creation protects another task's revision. Mode is set at creation.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(canonical_json_bytes(record))
    return path


def main(argv: list[str] | None = None) -> int:
    """Save or resume one explicitly supplied local teaching checkpoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("save", "resume"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--expected-revision", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == "save":
            if args.input is None:
                parser.error("save requires --input")
            payload = json.loads(args.input.read_text(encoding="utf-8"))
            LOGGER.info(
                "Saved %s",
                save_checkpoint(
                    args.directory, payload, expected_revision=args.expected_revision
                ),
            )
        else:
            LOGGER.info(
                "%s", json.dumps(read_checkpoint(args.directory), ensure_ascii=False)
            )
    except (ValueError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
