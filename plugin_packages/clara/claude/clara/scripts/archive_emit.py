"""Record Vera-owned CLI and MCP payloads before returning them to the host."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from archive_report_store import RunStore, digest
from archive_reporting import record_send
from selective_reporting import report_pipeline

__all__ = ["bound_run", "bind_output", "record_output", "main"]

# These are product routing identities, not classifications of user intent.
_COMPONENT_PIPELINES = {
    "client-file-preparation": {"fatture-xml-check"},
    "browser-automation": {"agenzia-acquisition"},
    "report-builder": {"financial-report-builder", "report-enti-locali"},
}


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _binding_values(arguments: Any):
    """Read documented case bindings, not paths embedded in source evidence."""
    names = {
        "client_engagement",
        "client_engagement_path",
        "context_path",
        "run_root",
        "output_dir",
        "output_directory",
        "output",
        "review_payload_path",
    }
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            if key in names and isinstance(value, str):
                yield value
            elif key in {
                "request",
                "token_owner",
                "run_intake",
                "client_engagement",
            } and isinstance(value, dict):
                yield from _binding_values(value)
        return
    if isinstance(arguments, list):
        explicit = []
        for index, value in enumerate(arguments):
            if not isinstance(value, str):
                continue
            flag, separator, assigned = value.partition("=")
            if flag.removeprefix("--").replace("-", "_") in names:
                if separator:
                    explicit.append(assigned)
                elif index + 1 < len(arguments):
                    explicit.append(arguments[index + 1])
        yield from _strings(explicit or arguments)


def _run_roots(arguments: Any) -> set[Path]:
    """Resolve explicit absolute case paths, never chat state or host activity."""
    roots = set()
    for value in _binding_values(arguments):
        if value.startswith("--") and "=" in value:
            value = value.partition("=")[2]
        if len(value) > 4096 or "\n" in value or not Path(value).is_absolute():
            continue
        # Resolve ordinary interpreter/system aliases too: they are not case
        # bindings. The producer independently validates its selected input path.
        candidate = Path(value).resolve()
        for parent in (candidate, *candidate.parents):
            if (
                parent.parent.name == "runs"
                and (parent / "context.json").is_file()
                and (parent / "run.json").is_file()
            ):
                roots.add(parent)
                break
    return roots


def _packet_recorded(root: Path, payload: Any) -> bool:
    """Archive's packet API already records its exact data before returning it."""
    from archive_reporting import _pieces

    pieces = _pieces(payload)
    if not pieces:
        return False
    events = {item["event_id"]: item for item in RunStore(root).events()}
    for piece in pieces:
        if not isinstance(piece, dict) or not isinstance(
            piece.get("vera_reporting"), dict
        ):
            return False
        binding = piece["vera_reporting"]
        event = events.get("send:" + str(binding.get("token")))
        if (
            binding.get("run_id") != root.name
            or event is None
            or event["response_sha256"] != digest(piece)
        ):
            return False
    return True


def bound_run(component: str, arguments: Any) -> Path | None:
    """Require a matching, started run when an eligible case is explicitly bound."""
    if component == "studio-archive":
        return None  # Archive records its own public results and exact read packets.
    pipelines = _COMPONENT_PIPELINES.get(component, {report_pipeline(component)}) - {
        None
    }
    if not pipelines:
        return None
    roots = _run_roots(arguments)
    if not roots:
        return None  # Dependency checks and standalone utilities have no case run.
    if len(roots) != 1:
        raise ValueError("Outgoing payload has more than one Archive run")
    root = roots.pop()
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    pipeline = report_pipeline(run["workflow_id"])
    if pipeline is None:
        return None
    if pipeline not in pipelines:
        raise ValueError("Outgoing payload belongs to another pipeline")
    state = RunStore(root).state()
    if state is None:
        raise ValueError("Outgoing payload requires Archive's start record")
    if state["collection_closed"]:
        return None  # Reopening a sealed result does not rewrite the completed run.
    return root


def bind_output(component: str, arguments: Any) -> dict[str, Any] | None:
    """Pin the active run and revision before an owned operation starts."""
    root = bound_run(component, arguments)
    if root is None:
        return None
    return {
        "run_root": str(root),
        "report_revision": RunStore(root).state()["report_revision"],
    }


def record_output(
    component: str,
    arguments: Any,
    payload: Any,
    *,
    channel: str,
    binding: dict[str, Any] | None = None,
) -> Path | None:
    """Use explicit run bindings and exclude MCP app-only metadata from sends."""
    root = bound_run(component, arguments)
    if binding is not None and (root is None or str(root) != binding["run_root"]):
        raise ValueError("Archive run closed or changed before its result was sent")
    if root is None:
        return None
    if channel == "mcp" and isinstance(payload, dict):
        producer_records = payload.get("_meta", {}).get("vera_source_records")
        private_sha256 = payload.get("_meta", {}).get("vera_source_review_sha256")
        payload = {
            key: value
            for key, value in payload.items()
            if key in {"content", "structuredContent", "isError"}
        }
        if producer_records is not None and isinstance(private_sha256, str):
            from archive_projection import register_row_projection

            register_row_projection(
                component,
                root / "outputs",
                payload,
                producer_records,
                private_sha256=private_sha256,
            )
    if not _packet_recorded(root, payload):
        record_send(
            root,
            payload,
            channel=channel + ":" + component,
            request=arguments,
            expected_revision=binding["report_revision"] if binding else None,
        )
    return root


def main() -> int:
    """The producer blocks payload delivery if its reporting write fails."""
    try:
        envelope = json.load(sys.stdin)
        if envelope.get("action") == "bind":
            sys.stdout.write(
                json.dumps(bind_output(envelope["component"], envelope["arguments"]))
                + "\n"
            )
            return 0
        root = record_output(
            envelope["component"],
            envelope["arguments"],
            envelope["payload"],
            channel=envelope["channel"],
            binding=envelope.get("binding"),
        )
        sys.stdout.write(json.dumps({"run_root": str(root) if root else None}) + "\n")
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        sys.stderr.write("Vera sending record failed: " + type(exc).__name__ + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
