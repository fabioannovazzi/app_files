"""Actual Windows job, pipe, timeout, and descendant lifecycle regressions."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "windows_worker_process",
    ROOT / "plugins/journal-bank-reconciliation/scripts/windows_worker_process.py",
)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)
pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Requires native Windows Job Objects"
)


def run(code, tmp_path, **kwargs):
    return worker.run_captured(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        stdin_path=kwargs.pop("stdin_path", None),
        stdout_limit=1024,
        stderr_limit=1024,
        timeout_seconds=kwargs.pop("timeout_seconds", 5),
        environment=os.environ,
        **kwargs,
    )


def test_pipe_capture_preserves_bytes_input_and_return_code(tmp_path):
    source = tmp_path / "entrée.txt"
    source.write_bytes("caffè\n".encode())
    result = run(
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); sys.stderr.buffer.write(b'error'); sys.exit(7)",
        tmp_path,
        stdin_path=source,
    )
    assert result["stdout"] == source.read_bytes()
    assert result["stderr"] == b"error"
    assert result["return_code"] == 7


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_capture_limit_stops_flood(stream, tmp_path):
    with pytest.raises(ValueError, match="byte limit"):
        run(f"import sys; sys.{stream}.buffer.write(b'x' * 10000000)", tmp_path)


def test_timeout_terminates_descendants(tmp_path):
    marker = tmp_path / "escaped.txt"
    child = f"import time; time.sleep(2); open({str(marker)!r},'w').write('escaped')"
    code = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
    with pytest.raises(ValueError, match="time limit"):
        run(code, tmp_path, timeout_seconds=1)
    time.sleep(1.3)
    assert not marker.exists()


def test_success_also_closes_detached_descendants(tmp_path):
    marker = tmp_path / "escaped.txt"
    child = f"import time; time.sleep(1); open({str(marker)!r},'w').write('escaped')"
    code = f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child!r}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags={getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',512)})"
    assert run(code, tmp_path)["return_code"] == 0
    time.sleep(1.2)
    assert not marker.exists()


def test_assignment_failure_never_executes_command(tmp_path, monkeypatch):
    marker = tmp_path / "must-not-run"

    def reject(self, process):
        raise OSError("job assignment denied")

    monkeypatch.setattr(worker._Job, "assign", reject)
    with pytest.raises(OSError, match="assignment denied"):
        run(f"open({str(marker)!r},'w').write('executed')", tmp_path)
    assert not marker.exists()
