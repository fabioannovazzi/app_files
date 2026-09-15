from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2] / "plugins/clara/scripts/bounded_process.py"
)


def runner():
    spec = importlib.util.spec_from_file_location("clara_bounded_process_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_process


def test_timeout_stops_descendant_before_it_can_write(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-survived"
    ready = tmp_path / "child-started"
    child = (
        "import time; from pathlib import Path; Path(%r).write_text('ready'); time.sleep(2); Path(%r).write_text('survived')"
        % (str(ready), str(marker))
    )
    parent = (
        "import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', %r]); time.sleep(30)"
        % child
    )
    run = runner()

    with pytest.raises(subprocess.TimeoutExpired):
        run([sys.executable, "-c", parent], timeout=0.5, capture_output=True)

    assert ready.exists(), "Synthetic descendant must start before cancellation"
    time.sleep(2)
    assert not marker.exists()


def test_capture_is_bounded_and_nonzero_exit_preserved() -> None:
    run = runner()

    result = run(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x'*100000); sys.stderr.write('failure'); sys.exit(3)",
        ],
        timeout=5,
        capture_output=True,
    )

    assert result.returncode == 3
    assert len(result.stdout) == 65536
    assert result.stderr == "failure"


def test_check_raises_with_captured_diagnostics() -> None:
    run = runner()

    with pytest.raises(subprocess.CalledProcessError, match="exit status 2") as error:
        run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('failed'); sys.exit(2)",
            ],
            timeout=5,
            check=True,
            capture_output=True,
        )

    assert error.value.stderr == "failed"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX SIGTERM protocol; Windows tree termination uses taskkill",
)
def test_parent_sigterm_runs_descendant_cleanup(tmp_path: Path) -> None:
    ready = tmp_path / "child-started"
    marker = tmp_path / "descendant-survived"
    child = (
        "import time; from pathlib import Path; Path(%r).write_text('ready'); time.sleep(2); Path(%r).write_text('survived')"
        % (str(ready), str(marker))
    )
    parent = (
        "import sys; sys.path.insert(0, %r); from bounded_process import run_process; run_process([sys.executable, '-c', %r], timeout=30)"
        % (str(SCRIPT.parent), child)
    )
    process = subprocess.Popen(
        [sys.executable, "-c", parent],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "Synthetic child did not start"

        process.terminate()
        returncode = process.wait(timeout=5)

        time.sleep(2)
        assert returncode != 0
        assert not marker.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
