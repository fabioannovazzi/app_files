"""Run a verified helper while collecting source-bound technical failure events.

Argument values, exception values, locals, professional stdout and file contents
are never serialized. Exact source coordinates, developer-authored error templates,
parser option names and OS error numbers are mechanical evidence. The host model
reviews retained stderr when those facts do not establish the complete cause.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import runpy
import sys
from pathlib import Path
from types import TracebackType
from typing import Any, NoReturn

__all__ = ["main", "exception_events"]


def _template(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            (
                value.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
                else "{value}"
            )
            for value in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _template(node.left)
    if isinstance(node, ast.Call) and node.args:
        return _template(node.args[0])
    return None


def _source(path: Path, line: int, root: Path) -> tuple[str, str | None] | None:
    """Read installed source, never an arbitrary diagnostic or client source file."""
    try:
        relative = path.resolve().relative_to(root.resolve())
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, SyntaxError, UnicodeError):
        return None
    candidates = [
        node
        for node in ast.walk(tree)
        if getattr(node, "lineno", 0) <= line <= getattr(node, "end_lineno", 0)
        and (
            isinstance(node, ast.Raise)
            or (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"error", "exception", "critical"}
            )
        )
    ]
    candidates.sort(
        key=lambda node: (
            0 if isinstance(node, ast.Raise) else 1,
            getattr(node, "end_lineno", 0) - getattr(node, "lineno", 0),
        )
    )
    for node in candidates:
        value = (
            _template(node.exc)
            if isinstance(node, ast.Raise) and node.exc
            else _template(node)
        )
        if value:
            return relative.as_posix(), value
    return relative.as_posix(), None


def exception_events(error: BaseException, root: Path) -> list[dict[str, Any]]:
    """Capture the actual exception chain without serializing dynamic values."""
    events = []
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        frames = []
        message = None
        trace: TracebackType | None = error.__traceback__
        while trace is not None:
            found = _source(
                Path(trace.tb_frame.f_code.co_filename), trace.tb_lineno, root
            )
            if found:
                frames.append(
                    {
                        "file": found[0],
                        "line": trace.tb_lineno,
                        "function": trace.tb_frame.f_code.co_name,
                    }
                )
                if found[1]:
                    message = found[1]
            trace = trace.tb_next
        if frames:
            events.append(
                {
                    "error_type": type(error).__name__,
                    "error_code": "execution.exception",
                    "message": message
                    or "Exception at the recorded package source location; dynamic detail retained for review.",
                    "errno": error.errno if isinstance(error, OSError) else None,
                    "technical_frames": frames,
                    "detail_available": (
                        message is not None and "{value}" not in message
                    )
                    or isinstance(error, OSError),
                }
            )
        error = error.__cause__ or error.__context__  # type: ignore[assignment]
    return events


def main() -> int:
    """Preserve helper argv, imports, stdout, exit status and ordinary stderr."""
    root, destination, script = (Path(value).resolve() for value in sys.argv[1:4])
    script.relative_to(root)
    arguments = sys.argv[4:]
    events: list[dict[str, Any]] = []
    original_error = argparse.ArgumentParser.error
    original_handle = logging.Logger.handle

    def parser_error(parser: argparse.ArgumentParser, message: str) -> NoReturn:
        context = sys.exception()
        cause = exception_events(context, root) if context else []
        if cause:
            events.extend(cause)
        else:
            provided = {
                value.partition("=")[0] for value in arguments if value.startswith("-")
            }
            actions = parser._actions
            missing = [
                action.option_strings[0] if action.option_strings else action.dest
                for action in actions
                if action.required
                and action.option_strings
                and not provided.intersection(action.option_strings)
            ]
            known = sorted(provided.intersection(parser._option_string_actions))
            detail = (
                "Missing required options: " + ", ".join(missing)
                if missing
                else "Command argument validation failed. Provided declared options: "
                + ", ".join(known)
            )
            events.append(
                {
                    "error_type": "ArgumentValidationError",
                    "error_code": "execution.arguments",
                    "message": detail,
                    "technical_frames": [],
                    "detail_available": bool(missing),
                }
            )
        original_error(parser, message)

    class Errors(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno < logging.ERROR:
                return
            current = sys.exception()
            if current is not None:
                events.extend(exception_events(current, root))
                return
            source = _source(Path(record.pathname), record.lineno, root)
            if source and source[1]:
                events.append(
                    {
                        "error_type": "LoggedExecutionError",
                        "error_code": "execution.logged-error",
                        "message": source[1],
                        "technical_frames": [
                            {
                                "file": source[0],
                                "line": record.lineno,
                                "function": record.funcName,
                            }
                        ],
                        "detail_available": not bool(record.args)
                        and "{value}" not in source[1],
                    }
                )

    setattr(argparse.ArgumentParser, "error", parser_error)
    handler = Errors()

    def handle(logger: logging.Logger, record: logging.LogRecord) -> None:
        # Adding a root handler would suppress the helper's basicConfig().
        # Observe records without changing its handlers, levels or formatting.
        if record.levelno >= logging.ERROR:
            handler.emit(record)
        original_handle(logger, record)

    setattr(logging.Logger, "handle", handle)
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *arguments]
    result = 0
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as error:
        result = (
            error.code
            if isinstance(error.code, int)
            else (0 if error.code is None else 1)
        )
        if result and not events:
            events.extend(exception_events(error, root))
        if not isinstance(error.code, (int, type(None))):
            sys.stderr.write(str(error.code) + "\n")
    finally:
        setattr(logging.Logger, "handle", original_handle)
        setattr(argparse.ArgumentParser, "error", original_error)
        # On an unhandled exception, sys.exception() is still available in finally.
        current = sys.exception()
        if current is not None and not isinstance(current, SystemExit):
            events.extend(exception_events(current, root))
        if result or current is not None:
            unique = list(
                {json.dumps(event, sort_keys=True): event for event in events}.values()
            )
            payload = {
                "events": unique,
                "capture_complete": bool(unique)
                and all(event["detail_available"] for event in unique),
                "worker_runtime_version": sys.version.split()[0],
                "worker_platform": {
                    "darwin": "macos",
                    "win32": "windows",
                    "linux": "linux",
                }.get(sys.platform, "unknown"),
            }
            with destination.open("x", encoding="utf-8") as sink:
                if os.name == "posix":
                    destination.chmod(0o600)
                json.dump(payload, sink)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
