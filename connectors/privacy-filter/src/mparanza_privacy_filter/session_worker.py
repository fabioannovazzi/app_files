"""Use upstream token allocation and restoration; private state stays on disk."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import FilterError
from .extract import extract_text

__all__ = ["execute", "main"]


def _lethe(request: dict[str, Any]) -> dict[str, Any]:
    from lethe.core import Item, assign_tokens, build_replacer, build_restorer

    folder = Path(request["folder"])
    state = folder / "lethe.json"
    operation = request["operation"]
    if operation == "create":
        review = json.loads(Path(request["state_path"]).read_text(encoding="utf-8"))
        if set(review) != {"approved", "items"} or review["approved"] is not True:
            raise FilterError("local_review_required")
        raw_items = review["items"]
        if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 20000:
            raise FilterError("invalid_local_review")
        for item in raw_items:
            # Validate shape only; names, aliases and inclusion remain the local review's decision.
            if (
                not isinstance(item, dict)
                or not set(item).issubset(
                    {
                        "type",
                        "canonical",
                        "surfaces",
                        "source",
                        "count",
                        "include",
                        "token",
                    }
                )
                or not isinstance(item.get("type"), str)
                or not isinstance(item.get("canonical"), str)
                or not isinstance(item.get("surfaces"), list)
                or any(not isinstance(surface, str) for surface in item["surfaces"])
                or item.get("source") not in ("dictionary", "pattern", "suggestion")
                or type(item.get("include", True)) is not bool
                or type(item.get("count", 0)) is not int
                or item.get("count", 0) < 0
            ):
                raise FilterError("invalid_local_review")
        items = [Item(**item) for item in raw_items]
        # Lethe allocates once for the complete reviewed job, never per document.
        assign_tokens(items)
        state.write_text(json.dumps([asdict(item) for item in items]), encoding="utf-8")
        return {"created": True}
    items = [Item(**item) for item in json.loads(state.read_text(encoding="utf-8"))]
    replacer, mapping = build_replacer(items)
    text = extract_text(Path(request["path"]))
    if operation == "filter":
        filtered, count = replacer(text)
        return {
            "redacted_text": filtered,
            "detection_counts": {"entities": count},
            "source_characters": len(text),
        }
    restorer = build_restorer(mapping)
    restored, _ = restorer(text)
    Path(request["target"]).write_text(restored, encoding="utf-8")
    return {"restored": True}


def _shield_command(model_root: Path, folder: Path, args: list[str]) -> str:
    config = json.loads((model_root / "shield.json").read_text())
    env = dict(os.environ)
    env.update(
        PII_SHIELD_DATA_DIR=str(model_root / "upstream"),
        PII_SHIELD_MODELS_DIR=str(model_root / "upstream/models"),
        PII_SHIELD_MAPPINGS_DIR=str(folder / "mappings"),
        PII_AUDIT_STDERR="false",
        NO_COLOR="1",
    )
    result = subprocess.run(  # nosec B603
        [config["node"], config["cli"], *args],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=590,
        check=False,
    )
    if result.returncode != 0:
        raise FilterError("shield_processing_failed")
    return result.stdout


def _shield(request: dict[str, Any]) -> dict[str, Any]:
    from .shield_ready import ready

    folder, model_root = Path(request["folder"]), Path(request["model_root"])
    if not ready(model_root):
        raise FilterError("shield_not_prepared")
    state = folder / "shield-session.json"
    operation = request["operation"]
    if operation == "create":
        state.write_text('{"upstream_id": null}', encoding="utf-8")
        return {"created": True}
    sid = json.loads(state.read_text())["upstream_id"]
    # Only the anonymizer's ID is accepted; there is no latest-session fallback.
    if sid is not None and (
        not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", sid)
    ):
        raise FilterError("invalid_upstream_session")
    text = extract_text(Path(request["path"]))
    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        work = Path(temporary)
        source = work / "document.txt"
        source.write_text(text, encoding="utf-8")
        if operation == "restore":
            if sid is None:
                raise FilterError("empty_session")
            _shield_command(
                model_root,
                folder,
                [
                    "deanonymize",
                    str(source),
                    "--session",
                    sid,
                    "--out",
                    request["target"],
                ],
            )
            return {"restored": True}
        args = [
            "anonymize",
            str(source),
            "--out",
            str(work / "output"),
            "--no-review",
            "--json",
        ]
        if sid is not None:
            args.extend(("--session", sid))
        body = json.loads(_shield_command(model_root, folder, args))
        new_sid = body["session_id"]
        if (
            not isinstance(new_sid, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", new_sid)
            or (sid is not None and new_sid != sid)
            or body["ner_ready"] is not True
            or body["files_count"] != 1
            or len(body["results"]) != 1
        ):
            raise FilterError("invalid_shield_response")
        output = Path(body["results"][0]["output_path"])
        if output.is_symlink() or not output.resolve().is_relative_to(work / "output"):
            raise FilterError("invalid_shield_response")
        filtered = output.read_text(encoding="utf-8")
        state.write_text(json.dumps({"upstream_id": new_sid}), encoding="utf-8")
        return {
            "redacted_text": filtered,
            "detection_counts": {"entities": body["entity_count"]},
            "source_characters": len(text),
        }


def execute(request: dict[str, Any]) -> dict[str, Any]:
    """Select only supported upstream adapters and operations."""
    if request["operation"] not in ("create", "filter", "restore"):
        raise FilterError("unsupported_session_operation")
    if request["engine"] == "lethe":
        return _lethe(request)
    if request["engine"] == "pii-shield":
        return _shield(request)
    raise FilterError("unsupported_session_engine")


def main() -> None:
    """Return a fixed error without upstream text, exceptions or mapping values."""
    try:
        body = execute(json.load(sys.stdin))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ImportError,
        subprocess.TimeoutExpired,
    ):
        body = {"error": "session_processing_failed"}
    sys.stdout.write(json.dumps(body))


if __name__ == "__main__":
    main()
