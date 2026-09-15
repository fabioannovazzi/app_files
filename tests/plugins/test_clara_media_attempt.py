from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/clara/scripts"


def _command(root: Path, body: str) -> list[str]:
    return [
        sys.executable,
        "-c",
        "import sys,os,time; from pathlib import Path; sys.path.insert(0, %r); from render_attempt import media_attempt; root=Path(%r)\n%s"
        % (str(SCRIPTS), str(root), body),
    ]


def test_media_attempt_recovers_process_death_without_losing_stages(
    tmp_path: Path,
) -> None:
    killed = subprocess.run(
        _command(
            tmp_path,
            "with media_attempt(root) as work:\n (work/'partial.mp4').write_bytes(b'partial')\n os._exit(31)",
        ),
        timeout=10,
        capture_output=True,
        text=True,
    )
    interrupted = json.loads((tmp_path / "render_attempt.json").read_text())
    assert killed.returncode == 31
    assert interrupted["status"] == "running"

    recovered = subprocess.run(
        _command(
            tmp_path,
            "with media_attempt(root) as work:\n (work/'synthetic-stage').write_text('complete')",
        ),
        timeout=10,
        capture_output=True,
        text=True,
    )

    assert recovered.returncode == 0, recovered.stderr
    assert (
        Path(interrupted["stage_directory"]) / "partial.mp4"
    ).read_bytes() == b"partial"
    history = list((tmp_path / ".render-attempts").glob("recovered-*.json"))
    assert len(history) == 1
    assert json.loads(history[0].read_text())["status"] == "interrupted"
    assert (
        json.loads((tmp_path / "render_attempt.json").read_text())["status"]
        == "completed"
    )


def test_media_attempt_serializes_two_actual_processes(tmp_path: Path) -> None:
    body = "with media_attempt(root) as work:\n with (root/'order.log').open('a') as f: f.write(work.name+' start\\n')\n time.sleep(0.3)\n with (root/'order.log').open('a') as f: f.write(work.name+' end\\n')"
    first = subprocess.Popen(
        _command(tmp_path, body),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    second = subprocess.Popen(
        _command(tmp_path, body),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _, first_error = first.communicate(timeout=10)
        _, second_error = second.communicate(timeout=10)
    finally:
        for process in (first, second):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    assert first.returncode == 0, first_error
    assert second.returncode == 0, second_error
    lines = (tmp_path / "order.log").read_text().splitlines()
    assert len(lines) == 4
    first_id = lines[0].split()[0]
    second_id = lines[2].split()[0]
    assert first_id != second_id
    assert lines == [
        f"{first_id} start",
        f"{first_id} end",
        f"{second_id} start",
        f"{second_id} end",
    ]


@pytest.mark.parametrize("name", [".media-render.lock", ".render-attempts"])
def test_media_attempt_rejects_symlink_control_paths(tmp_path: Path, name: str) -> None:
    root = tmp_path / "run"
    root.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    (root / name).symlink_to(target)

    result = subprocess.run(
        _command(root, "with media_attempt(root):\n pass"),
        timeout=10,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert list(target.iterdir()) == []
