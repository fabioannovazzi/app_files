"""Exercise the actual CLI recorder with real child stdout and private stderr."""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)

PRODUCT = Path(__file__).resolve().parents[2] / "plugins/vera"


@pytest.mark.parametrize("private_stderr", [True, False])
def test_cli_records_only_streams_it_releases_to_its_caller(
    archive_core, client_case, tmp_path, capfd, private_stderr
):
    from archive_cli import run_command

    loaded = start(archive_core, client_case, "report-builder")
    source = Path(loaded["context"]["input_bindings"][0]["path"])
    child = tmp_path / "producer.py"
    child.write_text(
        "import sys\nfrom pathlib import Path\nsys.stdout.write(Path(sys.argv[1]).read_text())\nsys.stderr.write('PRIVATE_DIAGNOSTIC')\n"
    )
    private = tmp_path / "retained.stderr"
    with private.open("w+", encoding="utf-8") as handle:
        result = run_command(
            [sys.executable, str(child), str(source)],
            plugin_root=PRODUCT,
            component="report-builder",
            arguments=["--client-engagement", loaded["context_path"]],
            stderr=handle if private_stderr else None,
            check=False,
        )

    streams = capfd.readouterr()
    assert result.returncode == 0
    assert streams.out == source.read_text()
    assert streams.err == ("" if private_stderr else "PRIVATE_DIAGNOSTIC")
    with sqlite3.connect(
        Path(loaded["run_root"]) / "reporting/events.sqlite3"
    ) as connection:
        events = [
            json.loads(row[0])
            for row in connection.execute("SELECT payload FROM events")
        ]
    sent = [event for event in events if event.get("channel") == "cli:report-builder"]
    assert len(sent) == 1
    assert sent[0]["local_response"] == (
        {"stdout": source.read_text()}
        if private_stderr
        else {"stdout": source.read_text(), "stderr": "PRIVATE_DIAGNOSTIC"}
    )
    assert private.read_text() == ("PRIVATE_DIAGNOSTIC" if private_stderr else "")


def test_cli_withholds_case_data_when_recording_storage_fails(
    archive_core, client_case, tmp_path, capfd, monkeypatch
):
    from archive_cli import run_command
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case, "report-builder")
    source = Path(loaded["context"]["input_bindings"][0]["path"])
    child = tmp_path / "producer.py"
    child.write_text(
        "import sys\nfrom pathlib import Path\nsys.stdout.write(Path(sys.argv[1]).read_text())\n"
    )

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic full disk")

    monkeypatch.setattr(RunStore, "event", unavailable)
    result = run_command(
        [sys.executable, str(child), str(source)],
        plugin_root=PRODUCT,
        component="report-builder",
        arguments=[loaded["context_path"]],
        check=False,
    )

    streams = capfd.readouterr()
    assert result.returncode == 70
    assert streams.out == ""
    assert source.read_text().strip() not in streams.err
    assert "case payload was not returned" in streams.err


def test_preview_startup_output_is_recorded_before_server_shutdown(
    archive_core, client_case, tmp_path
):
    from archive_report_store import RunStore

    loaded = start(archive_core, client_case, "management-control-pack")
    release = tmp_path / "release"
    child = tmp_path / "preview_report.py"
    child.write_text(
        "import sys,time\nfrom pathlib import Path\n"
        "sys.stdout.write('http://127.0.0.1:9000/report\\n');sys.stdout.flush()\n"
        "while not Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
    )
    launcher = tmp_path / "launcher.py"
    launcher.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0,{str(PRODUCT / 'scripts')!r})\n"
        "from archive_cli import run_command\n"
        f"raise SystemExit(run_command([sys.executable,{str(child)!r},{str(release)!r}],"
        f"plugin_root=Path({str(PRODUCT)!r}),component='management-control-pack',"
        f"arguments=[{str(child)!r},'--client-engagement',{loaded['context_path']!r}],check=False).returncode)\n"
    )
    received = queue.Queue()
    with subprocess.Popen(
        [sys.executable, str(launcher)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    ) as process:
        reader = threading.Thread(
            target=lambda: received.put(process.stdout.readline())
        )
        reader.start()
        try:
            line = received.get(timeout=10)
            assert process.poll() is None
            events = [
                event
                for event in RunStore(Path(loaded["run_root"])).events()
                if event.get("channel") == "cli:management-control-pack"
            ]
        finally:
            release.touch()
            reader.join(timeout=10)
            _, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, stderr
    assert line == "http://127.0.0.1:9000/report\n"
    assert len(events) == 1
    assert events[0]["bytes"] > 0
