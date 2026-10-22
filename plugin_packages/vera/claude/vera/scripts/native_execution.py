"""Execute published Vera helpers in the native service that owns their state."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import os
import queue
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import UUID

__all__ = ["execute", "serve", "main"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
_OWNED_WORKERS: list[subprocess.Popen] = []
_SHUTDOWN = globals().get("_SHUTDOWN", {"requested": False})


def _write(path: Path, value: Any) -> None:
    """Atomically retain job state; never replace a previous execution."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Execution job and task IDs must be UUIDs")
    return str(UUID(value))


def _jobs() -> Path:
    from operational_incidents import diagnostic_directory

    root = diagnostic_directory() / "executions"
    root.mkdir(mode=0o700, exist_ok=True)
    return root


def _specification(args: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    """Resolve only shipped Python helpers; never accept a shell or caller code."""
    components = json.loads((root / "components.json").read_text())["plugins"]
    component = args.get("component")
    if not isinstance(component, str) or component not in components:
        raise ValueError("Select a component in this installed Vera package")
    script = args.get("script", "scripts/check_dependencies.py")
    if (
        not isinstance(script, str)
        or PureWindowsPath(script).is_absolute()
        or "\\" in script
        or PurePosixPath(script).parts[:1] != ("scripts",)
        or ".." in PurePosixPath(script).parts
        or not script.endswith(".py")
    ):
        raise ValueError("Select a published component scripts/*.py entrypoint")
    component_root = root / "modules" / component
    if not component_root.exists():
        component_root = root.parent / component
    helper = component_root / script
    if helper.is_symlink() or not helper.resolve().is_relative_to(
        component_root.resolve()
    ):
        raise ValueError("Execution entrypoint is outside the selected component")
    if not helper.is_file():
        raise ValueError("Published component entrypoint does not exist")
    arguments = args.get("arguments", [])
    if not isinstance(arguments, list) or any(
        not isinstance(item, str) or "\0" in item for item in arguments
    ):
        raise ValueError("Helper arguments must be a list of strings")
    delivery = args.get("incident_delivery")
    if delivery not in {None, "local-only"}:
        raise ValueError("incident_delivery may only restrict delivery to local-only")
    requirements = args.get("requirements", [])
    if not isinstance(requirements, list) or any(
        not isinstance(item, str) for item in requirements
    ):
        raise ValueError("requirements must name published requirement files")
    for relative in requirements:
        selected = component_root / relative
        if (
            PureWindowsPath(relative).drive
            or not selected.resolve().is_relative_to(component_root.resolve())
            or selected.is_symlink()
            or not selected.is_file()
        ):
            raise ValueError("Requirements must belong to the selected component")
    return {
        "component": component,
        "script": script,
        "arguments": arguments,
        "task_id": _uuid(args.get("task_id", args["job_id"])),
        "incident_delivery": delivery,
        "requirements": requirements,
    }


def _arguments(spec: dict[str, Any]) -> list[str]:
    return [
        "--module",
        spec["component"],
        *[
            part
            for name in spec.get("requirements", [])
            for part in ("--requirements", name)
        ],
        "run",
        spec["script"],
        *spec["arguments"],
    ]


def _output(job: Path, *, streaming: bool = False) -> dict[str, Any]:
    result = job / "result.json"
    if result.is_file():
        value = json.loads(result.read_text(encoding="utf-8"))
        value["stdout"] = (job / "stdout.txt").read_text(encoding="utf-8")
        value["stderr"] = (job / "stderr.txt").read_text(encoding="utf-8")
        return value
    heartbeat = job / "heartbeat"
    fresh = heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < 15
    value = {
        "state": "running" if fresh else "interrupted_or_starting",
        "instruction": "Poll this job ID. Do not start another execution to recover a missing reply.",
    }
    # Long-lived preview helpers expose their startup URL while still running.
    # Preserve an incomplete UTF-8 tail until the next observation; never replace
    # bytes and then claim the replacement was the producer's actual output.
    for name in ("stdout", "stderr") if streaming else ():
        path = job / f"{name}.txt"
        if path.is_file():
            text = codecs.getincrementaldecoder("utf-8")().decode(
                path.read_bytes(), final=False
            )
            value[name] = text[: text.rfind("\n") + 1]
    if "stdout" in value or "stderr" in value:
        value.setdefault("stdout", "")
        value.setdefault("stderr", "")
    return value


def execute(args: dict[str, Any]) -> dict[str, Any]:
    """Start once or read a retained job, recording only the actual MCP reply."""
    if not isinstance(args, dict) or set(args) - {
        "operation",
        "job_id",
        "component",
        "script",
        "arguments",
        "task_id",
        "wait_seconds",
        "incident_delivery",
        "requirements",
    }:
        raise ValueError("Unknown execution arguments")
    job_id = _uuid(args["job_id"])
    operation = args["operation"]
    if operation not in {"run", "status", "cancel"}:
        raise ValueError("Execution operation must be run, status or cancel")
    wait = args.get("wait_seconds", 0)
    if type(wait) not in {int, float} or not 0 <= wait <= 20:
        raise ValueError("wait_seconds must be between zero and twenty")
    job = _jobs() / job_id
    if job.is_symlink():
        raise ValueError("Execution job directory is not a regular retained job")
    if operation == "run":
        spec = _specification(args)
        fingerprint = hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest()
        from archive_emit import bind_output

        binding = bind_output(spec["component"], _arguments(spec))
        execution_root = ROOT
        from verified_execution import bind_execution_run, execution_package_id

        if binding is not None:
            execution_root = bind_execution_run(Path(binding["run_root"]), ROOT)
            spec = _specification(args, execution_root)
        request = {
            **spec,
            "fingerprint": fingerprint,
            "binding": binding,
            "package_sha256": execution_package_id(execution_root),
        }
        try:
            job.mkdir(mode=0o700)
        except FileExistsError:
            previous = json.loads((job / "request.json").read_text())
            if previous["fingerprint"] != fingerprint:
                raise ValueError("This job ID already belongs to a different execution")
        else:
            _write(job / "request.json", request)
            if request["binding"] is not None:
                from archive_projection import register_model_arguments

                register_model_arguments(
                    spec["component"],
                    Path(request["binding"]["run_root"]) / "outputs",
                    spec["arguments"],
                )
            (job / "heartbeat").touch()
            # The native process inherits the host's permissions. Detachment only
            # keeps an authorized job alive when a tool connection is restarted.
            options = (
                {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            if os.name == "posix":
                from verified_execution import execution_lease_fds

                options["pass_fds"] = execution_lease_fds(execution_root)
            with (job / "runner.stderr").open("ab") as errors:
                worker = subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        str(execution_root / "scripts/native_execution.py"),
                        "--execute",
                        str(job),
                    ],
                    cwd=execution_root,
                    env={
                        **os.environ,
                        "VERA_EXECUTION_PACKAGE_ID": request["package_sha256"]
                        or "development",
                        "MPARANZA_INCIDENT_TASK_ID": spec["task_id"],
                        **(
                            {"MPARANZA_INCIDENT_DELIVERY": "local-only"}
                            if spec["incident_delivery"] == "local-only"
                            else {}
                        ),
                    },
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=errors,
                    **options,
                )
            _OWNED_WORKERS[:] = [item for item in _OWNED_WORKERS if item.poll() is None]
            _OWNED_WORKERS.append(worker)
            threading.Thread(target=worker.wait, daemon=True).start()
    elif set(args) - {"operation", "job_id", "wait_seconds"}:
        raise ValueError(
            "Status/cancel take only the retained job ID and optional wait"
        )
    request = json.loads((job / "request.json").read_text())
    if operation == "cancel" and not (job / "result.json").exists():
        (job / "cancel").touch()
    deadline = time.monotonic() + wait
    while not (job / "result.json").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    streaming = (request["component"], Path(request["script"]).name) in {
        ("management-control-pack", "preview_report.py"),
        ("open-item-reconciliation", "review_server.py"),
    }
    value = {
        "job_id": job_id,
        "package_sha256": request.get("package_sha256"),
        **_output(job, streaming=streaming),
    }
    if (job / "cancellation_error.json").exists():
        value["cancellation_error"] = json.loads(
            (job / "cancellation_error.json").read_text()
        )
    metadata = {
        key: item for key, item in value.items() if key not in {"stdout", "stderr"}
    }
    output = [metadata]
    if "stdout" in value:
        output.append({"stdout": value["stdout"], "stderr": value["stderr"]})
    payload = {"output": output}
    response: dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
    }
    if value.get("returncode", 0) != 0 or "cancellation_error" in value:
        response["isError"] = True
    if request["binding"] is not None:
        from archive_emit import record_output
        from archive_projection import register_metadata
        from archive_report_store import RunStore, digest

        store = RunStore(Path(request["binding"]["run_root"]))
        state = store.state()
        if state is not None and state["collection_closed"]:
            if operation == "cancel" or value.get("state") == "cancelled":
                # Cancellation is already requested above. Its service-owned
                # status can be confirmed without disclosing retained streams
                # or rewriting the closed professional-data report.
                payload = {"output": [metadata]}
                response = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": payload,
                }
                if "cancellation_error" in value:
                    response["isError"] = True
                return response
            # Read-only recovery of an already delivered exact result preserves
            # the sealed report. A newly completed payload still needs delivery
            # under its active revision and cannot silently enter a closed run.
            if any(
                event["kind"] == "vera_send"
                and event["response_sha256"] == digest(response)
                for event in store.events()
            ):
                return response

        # Only service-authored fields are metadata. Helper stdout/stderr must
        # keep their producer evidence, including unknown-content gaps.
        register_metadata(
            request["component"],
            Path(request["binding"]["run_root"]) / "outputs",
            metadata,
        )
        record_output(
            request["component"],
            _arguments(request),
            response,
            channel="mcp",
            binding=request["binding"],
        )
    return response


def _run(job: Path) -> int:
    request = json.loads((job / "request.json").read_text())
    stopped = threading.Event()

    def heartbeat() -> None:
        while not stopped.wait(2):
            (job / "heartbeat").touch()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    result = 1
    cancelled = False
    cancel_attempted = False
    try:
        with (
            (job / "stdout.txt").open("wb") as stdout,
            (job / "stderr.txt").open("wb") as stderr,
        ):
            try:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-B",
                        str(ROOT / "scripts/managed_python_runtime.py"),
                        *_arguments(request),
                    ],
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    env={
                        **os.environ,
                        "VERA_REPORTING_INTERNAL": "1",
                        "MPARANZA_INCIDENT_TASK_ID": request["task_id"],
                    },
                    **(
                        {
                            "creationflags": getattr(
                                subprocess, "CREATE_NEW_PROCESS_GROUP"
                            )
                        }
                        if os.name == "nt"
                        else {"start_new_session": True}
                    ),
                )
                while child.poll() is None:
                    if not cancel_attempted and (job / "cancel").exists():
                        cancel_attempted = True
                        try:
                            _stop(child, stderr)
                            cancelled = True
                            break
                        except (OSError, subprocess.SubprocessError) as error:
                            _write(
                                job / "cancellation_error.json",
                                {
                                    "type": type(error).__name__,
                                    "message": str(error),
                                },
                            )
                    time.sleep(0.05)
                result = child.wait()
            except OSError:
                stderr.write(traceback.format_exc().encode())
        _write(
            job / "result.json",
            {
                "state": (
                    "cancelled"
                    if cancelled
                    else "completed" if result == 0 else "failed"
                ),
                "returncode": result,
            },
        )
    finally:
        stopped.set()
        thread.join(timeout=3)
    return result


def _stop(child: subprocess.Popen, stderr: Any) -> None:
    """Stop only this runner's spawned process tree; retain partial output."""
    if os.name == "nt":
        system = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
        subprocess.run(
            [str(system), "/PID", str(child.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=stderr,
            stderr=stderr,
            check=True,
            timeout=10,
        )
    else:
        # Luna deliberately creates a separate process group. Include descendants
        # from the actual OS parent graph, not just the launcher's own group.
        listing = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid="],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        parents = {
            int(pid): int(parent)
            for pid, parent in (line.split() for line in listing.stdout.splitlines())
        }
        descendants = [child.pid]
        for parent in descendants:
            descendants.extend(pid for pid, owner in parents.items() if owner == parent)
        # Signal the launcher's group while its leader is still alive. On macOS,
        # signalling an empty group whose killed leader is not yet reaped can
        # return EPERM. Still stop each recorded descendant, including Luna's
        # separate group, and preserve genuine permission failures.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for pid in reversed(descendants):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
    child.wait(timeout=10)


def serve() -> None:
    """Serve bounded requests while detached workers retain their own results."""
    tool: dict[str, Any] = {
        "name": "vera_execute",
        "description": (
            "Run a published Vera component helper through the installed service. "
            "Use for dependency checks and the specialist's managed Python commands; "
            "the service owns persistent diagnostics outside the chat shell. "
            "For checks use script scripts/check_dependencies.py. Pass only the "
            "helper's arguments, with absolute client paths. Retain one job UUID "
            "per command and the workflow's task UUID. Poll status with that job UUID; "
            "repeating run with identical arguments never runs the command twice. "
            "On a user stop request, cancel that exact job and verify its terminal state. "
            "A running or interrupted job is not a successful result. "
            "Archive source review and Luna validation remain in the normal helper."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["operation", "job_id"],
            "properties": {
                "operation": {"type": "string", "enum": ["run", "status", "cancel"]},
                "job_id": {"type": "string", "format": "uuid"},
                "component": {"type": "string"},
                "script": {"type": "string"},
                "arguments": {"type": "array", "items": {"type": "string"}},
                "task_id": {"type": "string", "format": "uuid"},
                "incident_delivery": {"type": "string", "const": "local-only"},
                "requirements": {"type": "array", "items": {"type": "string"}},
                "wait_seconds": {"type": "number", "minimum": 0, "maximum": 20},
            },
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    }
    # A daemon reader lets transport shutdown stop intake even if the host
    # keeps stdin open or sends only part of a JSON line. The main thread
    # finishes an already accepted request and waits for its detached workers.
    messages: queue.Queue[str | None] = queue.Queue()

    def read_messages() -> None:
        try:
            for line in sys.stdin:
                messages.put(line)
        finally:
            messages.put(None)

    threading.Thread(target=read_messages, daemon=True).start()
    while not _SHUTDOWN["requested"]:
        try:
            line = messages.get(timeout=0.1)
        except queue.Empty:
            continue
        if line is None:
            break
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if "id" not in message:
            continue
        result: dict[str, Any]
        try:
            method = message["method"]
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "vera-execution", "version": "1.0.0"},
                    "instructions": tool["description"],
                }
            elif method == "tools/list":
                result = {"tools": [tool]}
            elif method == "ping":
                result = {}
            elif method == "tools/call" and message["params"]["name"] == tool["name"]:
                result = execute(message["params"].get("arguments", {}))
            else:
                raise ValueError("Unsupported Vera execution method")
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            # Process boundary: preserve concrete cause, never report success.
            result = {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"Vera execution {type(error).__name__}: {error}",
                    }
                ],
            }
        sys.stdout.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": result,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", type=Path)
    args = parser.parse_args()
    if args.execute is not None:
        return _run(args.execute)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: _SHUTDOWN.__setitem__("requested", True))
    try:
        serve()
    finally:
        # A disconnected host does not cancel persistent work. Keep this code
        # snapshot alive until every worker launched from it has finished.
        for worker in _OWNED_WORKERS:
            worker.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
