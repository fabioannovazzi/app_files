"""Bound Windows process trees and pipe capture without Unix selectors.

This is process lifecycle control, not a filesystem sandbox qualification.
The fixed gate cannot launch the requested command until the parent has placed
it in a kill-on-close Job Object, so descendants cannot escape a timeout race.
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from ctypes import wintypes as w
from pathlib import Path
from typing import Any

__all__ = ["run_captured"]

_GATE = """
import json, subprocess, sys
command, source = json.loads(sys.argv[1])
if sys.stdin.buffer.read(1) != b'G':
    raise SystemExit(125)
stream = open(source, 'rb') if source is not None else subprocess.DEVNULL
try:
    process = subprocess.Popen(command, stdin=stream)
    raise SystemExit(process.wait())
finally:
    if source is not None:
        stream.close()
"""


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", w.DWORD),
        ("min_working", ctypes.c_size_t),
        ("max_working", ctypes.c_size_t),
        ("processes", w.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", w.DWORD),
        ("scheduling", w.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t),
        ("peak_job", ctypes.c_size_t),
    ]


class _Job:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [
            w.HANDLE,
            ctypes.c_int,
            w.LPVOID,
            w.DWORD,
        ]
        self.api.SetInformationJobObject.restype = w.BOOL
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.AssignProcessToJobObject.restype = w.BOOL
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.api.CloseHandle.restype = w.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def run_captured(
    command: Sequence[str],
    *,
    cwd: Path,
    stdin_path: Path | None,
    stdout_limit: int,
    stderr_limit: int,
    timeout_seconds: int,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Capture bounded bytes; every exit closes the native descendant job."""

    if os.name != "nt":
        raise OSError("Native Windows process control is unavailable")
    if min(stdout_limit, stderr_limit, timeout_seconds) <= 0:
        raise ValueError("Worker limits must be positive")
    started = time.monotonic()
    env = dict(environment)
    for key in ("SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        if key in os.environ:
            env[key] = os.environ[key]
    job = _Job()
    process: subprocess.Popen[bytes] | None = None
    readers: list[threading.Thread] = []
    stop = threading.Event()
    messages: queue.Queue[tuple[str, bytes | OSError | None]] = queue.Queue(maxsize=4)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}

    def deliver(label: str, item: bytes | OSError | None) -> bool:
        while not stop.is_set():
            try:
                messages.put((label, item), timeout=0.05)
                return True
            except queue.Full:
                continue
        return False

    def read_pipe(label: str, stream: Any) -> None:
        try:
            while not stop.is_set():
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    break
                if not deliver(label, chunk):
                    return
        except OSError as exc:
            deliver(label, exc)
        finally:
            deliver(label, None)

    try:
        process = subprocess.Popen(  # nosec B603: argv is passed without a shell
            [
                sys.executable,
                "-I",
                "-c",
                _GATE,
                json.dumps(
                    [list(command), str(stdin_path) if stdin_path is not None else None]
                ),
            ],
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        job.assign(process)
        assert (
            process.stdin is not None
            and process.stdout is not None
            and process.stderr is not None
        )
        for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            reader = threading.Thread(
                target=read_pipe, args=(label, stream), daemon=True
            )
            reader.start()
            readers.append(reader)
        process.stdin.write(b"G")
        process.stdin.close()
        finished: set[str] = set()
        while len(finished) < 2:
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise ValueError("Worker process exceeded its time limit")
            try:
                label, chunk = messages.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if chunk is None:
                finished.add(label)
            elif isinstance(chunk, OSError):
                raise ValueError("Worker pipe capture failed") from chunk
            elif len(buffers[label]) + len(chunk) > limits[label]:
                raise ValueError(f"Worker {label} exceeded its byte limit")
            else:
                buffers[label].extend(chunk)
        remaining = max(0.01, timeout_seconds - (time.monotonic() - started))
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Worker process exceeded its time limit") from exc
        return {
            "return_code": return_code,
            "stdout": bytes(buffers["stdout"]),
            "stderr": bytes(buffers["stderr"]),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    finally:
        stop.set()
        job.close()
        if process is not None:
            if process.poll() is None:
                process.kill()  # Also handles failure to assign the gated process.
            process.wait(timeout=5)
            for reader in readers:
                reader.join(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
