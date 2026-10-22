"""Route review calls to the verified release pinned by each active Archive run."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, TextIO, cast

__all__ = ["serve"]


def serve(root: Path, node: str, component: str, shutdown: dict[str, bool]) -> int:
    """Retain one child per used release; never replay a mutation after failure."""
    from verified_execution import (
        bind_execution_run,
        execution_lease_fds,
        execution_package_id,
        release_execution_root,
    )

    children: dict[Path, subprocess.Popen] = {}
    leases: list[Path] = []
    token_roots: dict[str, Path] = {}
    output_lock = threading.Lock()
    incoming: queue.Queue = queue.Queue()
    initialization: dict[str, Any] | None = None
    readers: list[threading.Thread] = []
    pending: dict[Path, set[Any]] = {}
    pending_lock = threading.Lock()

    def token(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        selected = value.get("persistence_token") or value.get("review_reference")
        if isinstance(selected, dict):
            selected = selected.get("persistence_token") or selected.get("reference")
        return selected if isinstance(selected, str) else None

    def write(message: str) -> None:
        with output_lock:
            sys.stdout.write(message)
            sys.stdout.flush()

    def replies(child: subprocess.Popen, selected: Path) -> None:
        try:
            for line in cast(TextIO, child.stdout):
                message = json.loads(line)
                if message.get("id") == "runtime-initialize-" + selected.name:
                    continue
                with pending_lock:
                    pending[selected].discard(message.get("id"))
                result = message.get("result", {})
                reference = token(result.get("structuredContent"))
                if reference and result.get("isError") is not True:
                    token_roots[reference] = selected
                write(line)
        finally:
            with pending_lock:
                unanswered = tuple(pending[selected])
                pending[selected].clear()
            for request_id in unanswered:
                write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32000,
                                "message": "The pinned review service stopped before replying. Work may already be saved; inspect it before retrying.",
                            },
                        }
                    )
                    + "\n"
                )

    def child_for(selected: Path) -> subprocess.Popen:
        if selected in children:
            child = children[selected]
            if child.poll() is not None:
                raise RuntimeError(
                    "The pinned review service stopped; inspect saved work before reconnecting"
                )
            return child
        fds = execution_lease_fds(selected) if os.name == "posix" else ()
        child = subprocess.Popen(
            [node, str(selected / "scripts/component_service.cjs"), component],
            cwd=selected,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env={
                **os.environ,
                "VERA_EXECUTION_PACKAGE_ID": execution_package_id(selected)
                or "development",
                **({"VERA_CODE_LEASE_FD": str(fds[0])} if fds else {}),
            },
            pass_fds=fds,
        )
        children[selected] = child
        pending[selected] = set()
        thread = threading.Thread(target=replies, args=(child, selected), daemon=True)
        readers.append(thread)
        thread.start()
        if initialization is not None:
            cast(TextIO, child.stdin).write(
                json.dumps(
                    {**initialization, "id": "runtime-initialize-" + selected.name}
                )
                + "\n"
            )
            cast(TextIO, child.stdin).write(
                '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            )
            cast(TextIO, child.stdin).flush()
        return child

    def reader() -> None:
        for line in sys.stdin:
            incoming.put(line)
        incoming.put(None)

    threading.Thread(target=reader, daemon=True).start()
    try:
        while not shutdown["requested"]:
            try:
                line = incoming.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                break
            message = json.loads(line)
            try:
                selected = root
                if message.get("method") == "tools/call":
                    from archive_emit import bind_output

                    arguments = message["params"].get("arguments", {})
                    selected = token_roots.get(token(arguments) or "", root)
                    binding = bind_output(component, arguments)
                    if binding is not None:
                        selected = bind_execution_run(Path(binding["run_root"]), root)
                        leases.append(selected)
                child = child_for(selected)
                if "id" in message:
                    with pending_lock:
                        pending[selected].add(message["id"])
                cast(TextIO, child.stdin).write(line)
                cast(TextIO, child.stdin).flush()
                if message.get("method") == "initialize":
                    initialization = message
            except (OSError, ValueError, KeyError, RuntimeError) as error:
                with pending_lock:
                    pending.get(selected, set()).discard(message.get("id"))
                write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": message.get("id"),
                            "error": {"code": -32000, "message": str(error)},
                        }
                    )
                    + "\n"
                )
    finally:
        for child in children.values():
            if child.poll() is None:
                if shutdown["requested"]:
                    child.terminate()
                cast(TextIO, child.stdin).close()
            child.wait()
        for thread in readers:
            thread.join()
        for selected in leases:
            release_execution_root(selected)
    return 0
