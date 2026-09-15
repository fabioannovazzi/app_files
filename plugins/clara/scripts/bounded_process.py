"""Bound local renderer execution and terminate its owned process tree on cancellation."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator, Sequence

__all__ = ["run_process"]


def _stop_tree(process: subprocess.Popen[str]) -> None:
    """Kill the dedicated POSIX group or the Windows process tree, then reap."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


@contextmanager
def _termination_as_exception() -> Iterator[None]:
    """Let CLI termination run cancellation cleanup without replacing app handlers."""
    previous = signal.getsignal(signal.SIGTERM)
    install = (
        threading.current_thread() is threading.main_thread()
        and previous == signal.SIG_DFL
    )

    def terminate(signum: int, frame: object) -> None:
        raise InterruptedError("Renderer execution terminated")

    if install:
        signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        if install:
            signal.signal(signal.SIGTERM, previous)


def run_process(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    text: bool = True,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    check: bool = False,
    timeout: float,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Stream output to files and bound captured excerpts to 64 KiB per stream."""
    if not text or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(
            "Renderer execution requires text output and a positive timeout"
        )
    if capture_output and (stdout is not None or stderr is not None):
        raise ValueError("capture_output cannot be combined with explicit streams")
    with (
        _termination_as_exception(),
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as captured_out,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as captured_err,
    ):
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            text=True,
            stdout=captured_out if capture_output else stdout,
            stderr=captured_err if capture_output else stderr,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except BaseException:
            _stop_tree(process)
            raise
        captured_out.seek(0)
        captured_err.seek(0)
        result = subprocess.CompletedProcess(
            list(command),
            returncode,
            captured_out.read(65536) if capture_output else None,
            captured_err.read(65536) if capture_output else None,
        )
        if check:
            result.check_returncode()
        return result
