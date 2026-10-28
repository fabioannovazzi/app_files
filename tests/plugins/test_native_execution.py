"""Exercise native helper persistence, fixed code ownership and actual delivery."""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.build_product_mcp_catalog import add_product_mcp_catalog
from tests.plugins.test_vera_verified_execution import write_index

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def installed(tmp_path):
    """Isolate dependency provisioning; keep the real managed incident wrapper."""
    root = tmp_path / "installed"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    for source in (ROOT / "plugins/_shared/reporting-runtime").glob("*.py"):
        shutil.copyfile(source, scripts / source.name)
    for name in ("native_execution.py", "native_execution_mcp.cjs"):
        source = (
            Path(os.environ["NATIVE_EXECUTION_TEST_SOURCE"])
            if name == "native_execution.py"
            and os.environ.get("NATIVE_EXECUTION_TEST_SOURCE")
            else ROOT / "plugins/vera/scripts" / name
        )
        shutil.copyfile(source, scripts / name)
    (root / ".codex-plugin").mkdir()
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": "0.1.445"})
    )
    (root / "components.json").write_text(
        json.dumps({"plugins": ["fixture-component"]})
    )
    helper = root / "modules/fixture-component/scripts/check_dependencies.py"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        "import json,os,subprocess,sys,time\nfrom pathlib import Path\n"
        "path=Path(sys.argv[1]); path.write_text(path.read_text()+'run\\n' if path.exists() else 'run\\n')\n"
        "if '--child' in sys.argv:\n"
        "    program='import time,sys; from pathlib import Path; time.sleep(2); Path(sys.argv[1]).write_text(\"unexpected\")'\n"
        "    subprocess.Popen([sys.executable,'-c',program,str(path.with_name('late-child'))], start_new_session=os.name!='nt')\n"
        "    path.with_name('child-started').touch()\n"
        "time.sleep(float(sys.argv[2]) if len(sys.argv)>2 else 0)\n"
        "sys.stdout.write(json.dumps({'result':'fixture helper ran'})+'\\n')\n"
        "if '--fail' in sys.argv:\n"
        "    sys.stderr.write('Observed fixture failure\\n'); raise SystemExit(7)\n"
    )
    # Runtime provisioning has its own integration suite. This fixture only
    # replaces environment selection, executing real child processes and the
    # real incident wrapper/CLI delivery boundary.
    (root / "modules/fixture-component/requirements.txt").write_text("")
    runtime = scripts / "_managed_python_runtime.py"
    runtime.write_text(
        runtime.read_text() + "\ndef ensure_runtime(*args, **kwargs):\n"
        "    return True, Path(sys.prefix), 'Existing test interpreter'\n"
        "def runtime_python(target): return Path(sys.executable)\n"
        "def runtime_environment(target): return dict(os.environ)\n"
    )
    write_index(root)
    return root


def environment(tmp_path):
    temporary = tmp_path / "os-temp"
    temporary.mkdir(exist_ok=True)
    return {
        **os.environ,
        "TMPDIR": str(temporary),
        "TMP": str(temporary),
        "TEMP": str(temporary),
        "MPARANZA_RUNTIME_ROOT": str(tmp_path / "unused-runtime"),
        "MPARANZA_INCIDENT_STATE_DIR": str(tmp_path / "incidents"),
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }


@contextmanager
def native(root, tmp_path, entry="native_execution_mcp.cjs"):
    process = subprocess.Popen(
        ["node", str(root / "scripts" / entry)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment(tmp_path),
    )
    if entry == "on_demand_mcp.cjs":
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}
            )
            + "\n"
        )
        process.stdin.flush()
        assert "result" in json.loads(process.stdout.readline())

    def call(arguments):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "vera_execute", "arguments": arguments},
        }
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        assert line, process.stderr.read()
        return json.loads(line)["result"]

    try:
        yield call
    finally:
        process.stdin.close()
        process.wait(timeout=15)
        process.stdout.close()
        process.stderr.close()


def request(tmp_path, **values):
    return {
        "operation": "run",
        "job_id": str(uuid4()),
        "component": "fixture-component",
        "task_id": str(uuid4()),
        "arguments": [str(tmp_path / "counter")],
        "wait_seconds": 5,
        **values,
    }


def output(result):
    return result["structuredContent"]["output"]


def test_exact_run_retry_returns_saved_result_after_installed_component_is_removed(
    installed, tmp_path
):
    args = request(tmp_path)
    with native(installed, tmp_path) as call:
        first = call(args)
        assert output(first)[0]["state"] == "completed"
    shutil.rmtree(installed / "modules")
    (installed / "components.json").write_text(json.dumps({"plugins": []}))
    write_index(installed)  # A valid newer package, with this old component retired.
    with native(installed, tmp_path) as call:
        replay = call(args)
        different = call({**args, "arguments": ["different-request"]})

    assert replay.get("isError") is not True, replay
    assert output(replay) == output(first)
    assert different["isError"] is True
    assert "different execution" in json.dumps(different)
    assert (tmp_path / "counter").read_text() == "run\n"


@pytest.mark.parametrize("extra_arguments,expected_code", [([], 0), (["--fail"], 7)])
def test_closed_connection_retains_worker_code_then_releases_temporary_copies(
    installed, tmp_path, extra_arguments, expected_code
):
    temporary = tmp_path / "execution-temporary"
    temporary.mkdir()
    env = {
        **environment(tmp_path),
        "TMPDIR": str(temporary),
        "TMP": str(temporary),
        "TEMP": str(temporary),
    }
    args = request(
        tmp_path,
        arguments=[str(tmp_path / "counter"), "0.3", *extra_arguments],
        wait_seconds=0,
    )
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "vera_execute", "arguments": args},
    }

    result = subprocess.run(
        ["node", str(installed / "scripts/native_execution_mcp.cjs")],
        input=json.dumps(message) + "\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert output(json.loads(result.stdout)["result"])[0]["state"] == "running"
    retained = json.loads(
        (
            tmp_path
            / "incidents/helper-diagnostics/executions"
            / args["job_id"]
            / "result.json"
        ).read_text()
    )
    assert retained["returncode"] == expected_code
    assert (tmp_path / "counter").read_text() == "run\n"
    assert not list(temporary.glob("vera-*"))
    assert not list((temporary / ".vera-execution-leases").glob("*"))
    assert (installed / "scripts/native_execution.py").is_file()


@pytest.mark.parametrize("entry", ["native_execution_mcp.cjs", "on_demand_mcp.cjs"])
def test_native_helper_retains_diagnostics_and_runs_once_across_service_restart(
    installed, tmp_path, entry
):
    if entry == "on_demand_mcp.cjs":
        for name in (
            "on_demand_mcp.cjs",
            "mcp_service_client.cjs",
            "verify_mcp_package.cjs",
        ):
            shutil.copyfile(
                ROOT / "plugins/vera/scripts" / name, installed / "scripts" / name
            )
        (installed / "mcp-services.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "veraExecution": {
                            "command": "node",
                            "args": ["./scripts/native_execution_mcp.cjs"],
                        }
                    }
                }
            )
        )
        entries = {
            file.relative_to(installed).as_posix(): file.read_bytes()
            for file in installed.rglob("*")
            if file.is_file()
        }
        add_product_mcp_catalog(entries)
        (installed / "mcp-catalog.json").write_bytes(entries["mcp-catalog.json"])
        write_index(installed)
    args = request(
        tmp_path, arguments=[str(tmp_path / "counter"), "0.3"], wait_seconds=0
    )
    with native(installed, tmp_path, entry) as call:
        started = call(args)
        assert output(started)[0]["state"] == "running"
    with native(installed, tmp_path, entry) as call:
        finished = call(
            {"operation": "status", "job_id": args["job_id"], "wait_seconds": 5}
        )
        repeated = call(args)

    assert output(finished)[0]["state"] == "completed"
    assert output(finished)[0]["returncode"] == 0
    assert output(finished)[1]["stderr"] == ""
    assert json.loads(output(finished)[1]["stdout"]) == {"result": "fixture helper ran"}
    assert repeated == finished
    assert (tmp_path / "counter").read_text() == "run\n"
    state = json.loads((tmp_path / "incidents/state.json").read_text())
    assert any(key.startswith(args["task_id"] + ":") for key in state["operations"])


def test_native_standalone_helper_creates_task_from_product_root(installed, tmp_path):
    shutil.copyfile(
        ROOT / "plugins/vera/scripts/standalone_work.py",
        installed / "scripts/standalone_work.py",
    )
    shutil.copytree(
        ROOT / "plugins/_shared/vendor/modules/vera_assurance",
        installed / "vendor/modules/vera_assurance",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    write_index(installed)
    source = tmp_path / "question.txt"
    source.write_text("Synthetic legal question", encoding="utf-8")
    destination = tmp_path / "standalone-task"
    args = request(
        tmp_path,
        script="scripts/standalone_work.py",
        arguments=[
            "--destination",
            str(destination),
            "--workflow",
            "prompt-optimizer",
            "--source",
            str(source),
            "--label",
            "Standalone question",
            "--purpose",
            "Prepare a legal answer",
        ],
    )

    with native(installed, tmp_path) as call:
        result = call(args)

    assert output(result)[0]["returncode"] == 0
    context = json.loads(output(result)[1]["stdout"])
    assert Path(context["context_path"]).is_file()
    assert context["schema_version"] == "vera.standalone_workflow_context.v1"
    assert (
        Path(context["input_bindings"][0]["path"]).read_bytes() == source.read_bytes()
    )
    assert not list(destination.rglob("client.json"))


def test_active_job_survives_removal_of_its_installed_cache(installed, tmp_path):
    args = request(
        tmp_path, arguments=[str(tmp_path / "counter"), "0.4"], wait_seconds=0
    )
    with native(installed, tmp_path) as call:
        call(args)
        shutil.rmtree(installed)
        finished = call(
            {"operation": "status", "job_id": args["job_id"], "wait_seconds": 5}
        )

    assert output(finished)[0]["returncode"] == 0
    assert (tmp_path / "counter").read_text() == "run\n"


def test_failed_helper_keeps_exit_code_and_complete_stderr(installed, tmp_path):
    with native(installed, tmp_path) as call:
        result = call(
            request(
                tmp_path,
                arguments=[
                    str(tmp_path / "counter"),
                    "0",
                    "--fail",
                ],
            )
        )

    assert result["isError"] is True
    assert output(result)[0]["returncode"] == 7
    assert "Observed fixture failure\n" in output(result)[1]["stderr"]
    assert (tmp_path / "counter").read_text() == "run\n"
    state = json.loads((tmp_path / "incidents/state.json").read_text())
    assert state["outbox"][0]["operation"] == "report"


@pytest.mark.parametrize(
    "fields",
    [
        {"script": "../outside.py"},
        {"script": "/tmp/outside.py"},
        {"script": "scripts/../../outside.py"},
        {"script": "scripts/missing.py"},
        {"component": "not-in-this-package"},
        {"shell": "whoami"},
        {"script": "scripts/check_dependencies.py;whoami"},
    ],
)
def test_unowned_commands_are_rejected_before_execution(installed, tmp_path, fields):
    with native(installed, tmp_path) as call:
        result = call(request(tmp_path, **fields))

    assert result["isError"] is True
    assert not (tmp_path / "counter").exists()


def test_reused_job_id_cannot_launch_a_different_command(installed, tmp_path):
    args = request(tmp_path)
    with native(installed, tmp_path) as call:
        call(args)
        result = call({**args, "arguments": [str(tmp_path / "other-counter")]})

    assert result["isError"] is True
    assert "different execution" in result["content"][0]["text"]
    assert (tmp_path / "counter").read_text() == "run\n"
    assert not (tmp_path / "other-counter").exists()


@pytest.mark.parametrize(
    "group_signal_delay",
    [
        0,
        pytest.param(
            0.05,
            marks=pytest.mark.skipif(
                os.name == "nt", reason="POSIX process-group scheduling"
            ),
        ),
    ],
)
def test_cancel_stops_the_owned_helper_and_detached_descendant(
    installed, tmp_path, group_signal_delay
):
    if group_signal_delay:
        # Let an individually killed launcher reach its zombie state before the
        # group signal. macOS rejects signals to an empty, unreaped group with
        # EPERM; cancellation must not create that state itself.
        source = installed / "scripts/native_execution.py"
        source.write_text(
            source.read_text().replace(
                'if __name__ == "__main__":',
                "_original_killpg = os.killpg\n"
                "def _delayed_killpg(pid, sig):\n"
                f"    time.sleep({group_signal_delay!r})\n"
                "    return _original_killpg(pid, sig)\n"
                "os.killpg = _delayed_killpg\n\n"
                'if __name__ == "__main__":',
            )
        )
        write_index(installed)
    args = request(
        tmp_path,
        arguments=[str(tmp_path / "counter"), "5", "--child"],
        wait_seconds=0,
    )
    with native(installed, tmp_path) as call:
        call(args)
        deadline = time.monotonic() + 3
        while not (tmp_path / "child-started").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / "child-started").exists()

        cancelled = call(
            {"operation": "cancel", "job_id": args["job_id"], "wait_seconds": 5}
        )
        repeated = call(args)

    assert output(cancelled)[0]["state"] == "cancelled", cancelled
    assert output(cancelled)[0]["returncode"] != 0
    assert repeated == cancelled
    assert (tmp_path / "counter").read_text() == "run\n"
    time.sleep(2.2)
    assert not (tmp_path / "late-child").exists()


def test_bootstrap_rejects_changed_owned_code_before_loading_it(installed, tmp_path):
    source = installed / "scripts/verified_execution.py"
    source.write_text("raise RuntimeError('Unverified code was loaded')\n")

    result = subprocess.run(
        ["node", str(installed / "scripts/native_execution_mcp.cjs")],
        input="",
        text=True,
        capture_output=True,
        timeout=15,
        env=environment(tmp_path),
    )

    assert result.returncode != 0
    assert "does not match its build index" in result.stderr
    assert "Unverified code was loaded" not in result.stderr
    assert not (tmp_path / "incidents").exists()


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="Reproduce the observed macOS chat-shell boundary",
)
def test_native_state_writes_work_when_chat_shell_writes_are_denied(
    installed, tmp_path
):
    state = tmp_path / "incidents"
    state.mkdir()
    profile = (
        '(version 1)(allow default)(deny file-write* (subpath "'
        + str(state.resolve())
        + '"))'
    )
    shell = subprocess.run(
        [
            "sandbox-exec",
            "-p",
            profile,
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('test')",
            str(state / "probe"),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )

    with native(installed, tmp_path) as call:
        result = call(request(tmp_path))

    assert shell.returncode != 0
    assert "PermissionError" in shell.stderr
    assert output(result)[0]["state"] == "completed"
    assert output(result)[1]["stderr"] == ""
    assert (state / "state.json").is_file()


def test_native_service_releases_snapshot_after_last_persistent_job(
    installed, tmp_path
):
    args = request(
        tmp_path, arguments=[str(tmp_path / "counter"), "0.5"], wait_seconds=0
    )
    temporary = tmp_path / "os-temp"
    with native(installed, tmp_path) as call:
        started = call(args)
        assert output(started)[0]["state"] == "running"
        assert list((tmp_path / "unused-runtime/code").glob("*/execution-files.json"))
        assert list(temporary.glob("vera-execution-bootstrap-*"))
    # Closing the transport waits for its worker, then releases only code.
    assert (tmp_path / "counter").read_text() == "run\n"
    assert not list(temporary.glob("vera-verified-*"))
    assert not list(temporary.glob("vera-execution-bootstrap-*"))
    with native(installed, tmp_path) as call:
        retained = call({"operation": "status", "job_id": args["job_id"]})
    assert output(retained)[0]["state"] == "completed"
    assert output(retained)[0]["returncode"] == 0
    assert (tmp_path / "counter").read_text() == "run\n"


def test_idle_native_service_releases_snapshot(installed, tmp_path):
    with native(installed, tmp_path):
        pass
    temporary = tmp_path / "os-temp"
    assert not list(temporary.glob("vera-verified-*"))
    assert not list(temporary.glob("vera-execution-bootstrap-*"))


@pytest.mark.skipif(
    os.name != "posix", reason="POSIX transport signals and flock leases"
)
@pytest.mark.parametrize("target", ["launcher", "group"])
@pytest.mark.parametrize("busy", [False, True])
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_termination_keeps_accepted_work_and_releases_code(
    installed, tmp_path, target, busy, signum
):
    process = subprocess.Popen(
        ["node", str(installed / "scripts/native_execution_mcp.cjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment(tmp_path),
        start_new_session=True,
    )
    args = request(
        tmp_path, arguments=[str(tmp_path / "counter"), "0.6"], wait_seconds=0
    )
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "vera_execute", "arguments": args},
    }
    if not busy:
        message = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    try:
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        assert json.loads(process.stdout.readline())["id"] == 1
        if not busy:
            process.stdin.write('{"jsonrpc":')
            process.stdin.flush()
        # Stdin remains open: a signal must stop intake by itself. Repeated
        # signals must not interrupt worker retention or delete its code.
        for _ in range(100):
            if target == "group":
                os.killpg(process.pid, signum)
            else:
                process.send_signal(signum)
        process.wait(timeout=15)
        assert process.returncode == 0, process.stderr.read()
        temporary = tmp_path / "os-temp"
        assert not list(temporary.glob("vera-*"))
        assert not list((temporary / ".vera-execution-leases").glob("*"))
        if busy:
            retained = json.loads(
                (
                    tmp_path
                    / "incidents/helper-diagnostics/executions"
                    / args["job_id"]
                    / "result.json"
                ).read_text()
            )
            assert retained["state"] == "completed"
            assert retained["returncode"] == 0
            assert (tmp_path / "counter").read_text() == "run\n"
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX kernel leases")
@pytest.mark.parametrize("busy", [False, True])
def test_sigkill_recovery_protects_detached_worker_then_recovers_orphan(
    installed, tmp_path, busy
):
    process = subprocess.Popen(
        ["node", str(installed / "scripts/native_execution_mcp.cjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment(tmp_path),
        start_new_session=True,
    )
    args = request(
        tmp_path, arguments=[str(tmp_path / "counter"), "1.5"], wait_seconds=0
    )
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "vera_execute", "arguments": args},
    }
    if not busy:
        message = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    try:
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        assert json.loads(process.stdout.readline())["id"] == 1
        temporary = tmp_path / "os-temp"
        snapshots = [
            path.parent
            for path in (tmp_path / "unused-runtime/code").glob(
                "*/execution-files.json"
            )
        ]
        assert len(snapshots) == 1
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        # A new service automatically recovers an unleased orphan. A detached
        # worker still holds its inherited lease, even after SIGKILL of owner.
        with native(installed, tmp_path):
            if busy:
                assert snapshots[0].exists()
        if busy:
            result_path = (
                tmp_path
                / "incidents/helper-diagnostics/executions"
                / args["job_id"]
                / "result.json"
            )
            deadline = time.monotonic() + 10
            while not result_path.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert json.loads(result_path.read_text())["returncode"] == 0
            assert (tmp_path / "counter").read_text() == "run\n"
            # The result is persisted just before the worker exits.
            time.sleep(0.2)
            with native(installed, tmp_path):
                pass
        assert not list(temporary.glob("vera-*"))
        assert not list((temporary / ".vera-execution-leases").glob("*"))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX inherited code leases")
@pytest.mark.parametrize("shared", [False, True])
def test_killed_cli_launcher_retains_helper_code_until_helper_finishes(
    installed, tmp_path, shared
):
    helper = installed / "modules/fixture-component/scripts/hold_code.py"
    helper.write_text(
        "import sys,time\nfrom pathlib import Path\n"
        "Path(sys.argv[1]).touch()\ntime.sleep(1.5)\n"
        "assert Path(__file__).read_text()\nPath(sys.argv[2]).touch()\n"
    )
    write_index(installed)
    started, finished = tmp_path / "started", tmp_path / "finished"
    program = (
        "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
        "from verified_execution import prepare_execution_root; "
        "from archive_cli import run_command; "
        f"root=prepare_execution_root(Path(sys.argv[2]),None,snapshot=True,shared={shared!r}); "
        "print(root,flush=True); "
        "run_command([sys.executable,str(root/'modules/fixture-component/scripts/hold_code.py'),sys.argv[3],sys.argv[4]],"
        "plugin_root=root,component='fixture-component',arguments=[],check=True)"
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            program,
            str(installed / "scripts"),
            str(installed),
            str(started),
            str(finished),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment(tmp_path),
        start_new_session=True,
    )
    initialize = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"

    def restart():
        result = subprocess.run(
            ["node", str(installed / "scripts/native_execution_mcp.cjs")],
            input=initialize,
            text=True,
            capture_output=True,
            env=environment(tmp_path),
            timeout=15,
        )
        assert result.returncode == 0, result.stderr

    try:
        snapshot = Path(process.stdout.readline().strip())
        deadline = time.monotonic() + 10
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started.exists()
        process.kill()
        process.wait(timeout=10)
        restart()
        assert snapshot.exists(), "A surviving CLI helper must retain its code lease"
        deadline = time.monotonic() + 10
        while not finished.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert (
            finished.exists()
        ), "The helper must still read its code after launcher death"
        time.sleep(0.1)
        restart()
        if shared:
            # Shared storage keeps two idle releases; explicit collection proves
            # that the terminated helper no longer holds its inherited lease.
            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    "import sys;sys.path.insert(0,sys.argv[1]);from verified_execution import collect_execution_store;collect_execution_store(keep_idle=0)",
                    str(installed / "scripts"),
                ],
                env=environment(tmp_path),
                check=True,
                timeout=15,
            )
        assert not snapshot.exists()
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize("method", ["initialize", "tools/list"])
def test_native_tool_discloses_standard_semantic_worker_without_weakening_controls(
    installed, tmp_path, method
):
    """The host must see the worker boundary before approving any execution."""
    message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}

    result = subprocess.run(
        ["node", str(installed / "scripts/native_execution_mcp.cjs")],
        input=json.dumps(message) + "\n",
        text=True,
        capture_output=True,
        env=environment(tmp_path),
        timeout=15,
        check=True,
    )

    reply = json.loads(result.stdout)["result"]
    description = (
        reply["instructions"]
        if method == "initialize"
        else reply["tools"][0]["description"]
    )
    assert "standard model-processing step" in description
    assert "not a separate user authorization step" in description
    assert "unresolved financial rows" in description
    assert "dates, signed amounts, names and references" in description
    assert "existing authenticated Codex model worker" in description
    assert "model provider/account configured in that host runtime" in description
    assert "normal client work as well as synthetic tests" in description
    assert "Host approval controls still apply" in description
    assert "do not bypass it or change execution routes" in description
    if method == "tools/list":
        tool = reply["tools"][0]
        assert tool["annotations"] == {
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        }
        assert tool["inputSchema"]["required"] == ["operation", "job_id"]
        assert "authorization" not in tool["inputSchema"]["properties"]
    assert not (tmp_path / "counter").exists()


def test_packaged_tool_catalog_retains_standard_semantic_processing_boundary(installed):
    """The normal product router must advertise the boundary before dispatch."""
    shutil.copyfile(
        ROOT / "plugins/vera/scripts/mcp_service_client.cjs",
        installed / "scripts/mcp_service_client.cjs",
    )
    entries = {
        file.relative_to(installed).as_posix(): file.read_bytes()
        for file in installed.rglob("*")
        if file.is_file()
    }
    entries["mcp-services.json"] = json.dumps(
        {
            "mcpServers": {
                "veraExecution": {
                    "command": "node",
                    "args": ["./scripts/native_execution_mcp.cjs"],
                }
            }
        }
    ).encode()

    add_product_mcp_catalog(entries)

    service = json.loads(entries["mcp-catalog.json"])["services"][0]
    tool = service["tools"][0]
    assert tool["name"] == "vera_execute"
    assert "not a separate user authorization step" in tool["description"]
    assert "that recipient is OpenAI" in tool["description"]
    assert "unresolved financial rows" in tool["description"]
    assert tool["annotations"]["openWorldHint"] is True
    assert service["initialize"]["instructions"] == tool["description"]
