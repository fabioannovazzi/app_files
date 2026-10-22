"""Real processes retain verified code across cache replacement and upgrades."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_vera_verified_execution import load_recovery, write_index

ROOT = Path(__file__).resolve().parents[2]


def package(tmp_path, version="1"):
    root = tmp_path / f"installed-{version}"
    (root / "scripts").mkdir(parents=True)
    (root / ".codex-plugin").mkdir()
    (root / ".codex-plugin/plugin.json").write_text(
        json.dumps({"name": "vera", "version": version})
    )
    (root / "scripts/helper.py").write_text(f"VERSION = {version!r}\n")
    write_index(root)
    return root


def test_repeated_acquisitions_share_one_copy_and_retain_other_holder(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    first, second = load_recovery(), load_recovery()
    source = package(tmp_path)
    pinned = first.prepare_execution_root(source, None, shared=True)
    other = second.prepare_execution_root(source, None, shared=True)
    shutil.rmtree(source)
    first.release_execution_root(pinned)
    first.collect_execution_store(keep_idle=0)
    assert pinned == other
    assert (other / "scripts/helper.py").read_text() == "VERSION = '1'\n"
    second.release_execution_root(other)
    first.collect_execution_store(keep_idle=0)
    assert not pinned.exists()


def test_new_release_does_not_replace_live_code_and_idle_storage_is_bounded(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    recovery = load_recovery()
    old = recovery.prepare_execution_root(package(tmp_path), None, shared=True)
    for version in range(2, 8):
        latest = recovery.prepare_execution_root(
            package(tmp_path, str(version)), None, shared=True
        )
        recovery.release_execution_root(latest)
    assert (old / "scripts/helper.py").read_text() == "VERSION = '1'\n"
    assert (latest / "scripts/helper.py").read_text() == "VERSION = '7'\n"
    assert len(list((tmp_path / "runtime/code").glob("*/execution-files.json"))) == 3
    recovery.release_execution_root(old)
    assert len(list((tmp_path / "runtime/code").glob("*/execution-files.json"))) == 2


def test_cached_code_tamper_is_rejected_before_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    recovery = load_recovery()
    source = package(tmp_path)
    pinned = recovery.prepare_execution_root(source, None, shared=True)
    helper = pinned / "scripts/helper.py"
    helper.chmod(0o600)
    helper.write_text("raise RuntimeError('must not execute')")
    with pytest.raises(ValueError, match="Shared execution code changed"):
        recovery.prepare_execution_root(source, None, shared=True)
    recovery.release_execution_root(pinned)


def review_package(tmp_path, version="1"):
    root = package(tmp_path, version)
    for name in (
        "native_execution_mcp.cjs",
        "run_component_mcp.cjs",
        "component_service.cjs",
        "component_gateway.py",
        "archive_emission_mcp.cjs",
        "verified_execution.py",
        "reporting_product.py",
    ):
        shutil.copyfile(ROOT / "plugins/vera/scripts" / name, root / "scripts" / name)
    (root / "usage").mkdir()
    (root / "usage/pipelines.json").write_text(
        json.dumps({"model_data_reporting": {"component_pipelines": {}}})
    )
    server = root / "modules/open-item-reconciliation/mcp/server.cjs"
    server.parent.mkdir(parents=True)
    server.write_text(
        'const fs=require("node:fs"),path=require("node:path");\n'
        'require("node:readline").createInterface({input:process.stdin}).on("line",line=>{\n'
        'const message=JSON.parse(line); if(message.id===undefined)return; const metadata=JSON.parse(fs.readFileSync(path.resolve(__dirname,"../../../.codex-plugin/plugin.json")));\n'
        'process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:message.id,result:{version:metadata.version,cwd:process.cwd()}})+"\\n");});\n'
    )
    write_index(root)
    return root


def launch_review(root, tmp_path):
    return subprocess.Popen(
        [
            "node",
            str(root / "scripts/run_component_mcp.cjs"),
            "open-item-reconciliation",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "MPARANZA_RUNTIME_ROOT": str(tmp_path / "runtime"),
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        },
    )


def call(process):
    process.stdin.write(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
    )
    process.stdin.flush()
    line = process.stdout.readline()
    assert line, process.stderr.read()
    return json.loads(line)["result"]


def stop(process):
    process.stdin.close()
    process.wait(timeout=15)
    errors = process.stderr.read()
    process.stdout.close()
    process.stderr.close()
    assert process.returncode == 0, errors


def test_live_review_reads_files_and_cwd_after_reinstall_and_upgrade(tmp_path):
    source = review_package(tmp_path)
    old = launch_review(source, tmp_path)
    new = None
    try:
        before = call(old)
        removed = source.with_name("plugin-backup")
        source.rename(removed)
        shutil.rmtree(removed)
        source = review_package(tmp_path)
        assert call(old) == before
        shutil.rmtree(source)
        source = review_package(tmp_path, "2")
        new = launch_review(source, tmp_path)
        assert call(new)["version"] == "2"
        assert call(old) == before
        assert before["version"] == "1"
        assert Path(before["cwd"]).is_dir()
    finally:
        stop(old)
        if new:
            stop(new)


def call_tool(process, run):
    process.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "review",
                    "arguments": {"client_engagement": str(run / "context.json")},
                },
            }
        )
        + "\n"
    )
    process.stdin.flush()
    line = process.stdout.readline()
    assert line, process.stderr.read()
    return json.loads(line)["result"]


def bound_review_package(tmp_path, version):
    root = review_package(tmp_path, version)
    (root / "scripts/archive_emit.py").write_text(
        "from pathlib import Path\n"
        "def bind_output(component, arguments):\n"
        "    return {'run_root':str(Path(arguments['client_engagement']).parent)}\n"
    )
    write_index(root)
    return root


def test_reconnected_review_uses_original_run_package_new_run_uses_upgrade(tmp_path):
    old_source = bound_review_package(tmp_path, "1")
    run = tmp_path / "run-original"
    run.mkdir()
    old = launch_review(old_source, tmp_path)
    try:
        assert call(old)["version"] == "1"
        assert call_tool(old, run)["version"] == "1"
    finally:
        stop(old)
    shutil.rmtree(old_source)
    new_source = bound_review_package(tmp_path, "2")
    fresh = tmp_path / "run-new"
    fresh.mkdir()
    new = launch_review(new_source, tmp_path)
    try:
        assert call(new)["version"] == "2"
        assert call_tool(new, run)["version"] == "1"
        assert call_tool(new, fresh)["version"] == "2"
    finally:
        stop(new)


def test_retired_package_does_not_silently_recalculate_with_new_release(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    recovery = load_recovery()
    source = package(tmp_path)
    current = recovery.prepare_execution_root(source, None, shared=True)
    run = tmp_path / "run"
    run.mkdir()
    bound = recovery.bind_execution_run(run, current)
    recovery.release_execution_root(bound)
    recovery.release_execution_root(current)
    recovery.collect_execution_store(keep_idle=0)
    newer = recovery.prepare_execution_root(package(tmp_path, "2"), None, shared=True)
    try:
        with pytest.raises(ValueError, match="original code is no longer retained"):
            recovery.bind_execution_run(run, newer)
    finally:
        recovery.release_execution_root(newer)


def test_concurrent_starts_publish_one_complete_copy(tmp_path, monkeypatch):
    monkeypatch.setenv("MPARANZA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    source = package(tmp_path)
    program = (
        "import runpy,sys,time; from pathlib import Path; "
        "m=runpy.run_path(sys.argv[1]); "
        "root=m['prepare_execution_root'](Path(sys.argv[2]),None,shared=True); "
        "print(root,flush=True); time.sleep(0.4); m['release_execution_root'](root)"
    )
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                program,
                str(ROOT / "plugins/vera/scripts/verified_execution.py"),
                str(source),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(6)
    ]
    results = [child.communicate(timeout=20) for child in children]
    assert all(child.returncode == 0 for child in children), results
    assert len({output for output, _ in results}) == 1
    assert len(list((tmp_path / "runtime/code").glob("*/execution-files.json"))) == 1
    assert not list((tmp_path / "runtime/code").glob(".staging-*"))


def test_every_registered_local_service_uses_a_protected_launcher():
    config = json.loads((ROOT / "plugins/vera/.mcp.json").read_text())
    launchers = {
        "./scripts/native_execution_mcp.cjs",
        "./scripts/run_component_mcp.cjs",
        "./scripts/run_service_mcp.cjs",
    }
    assert all(
        server["args"][0] in launchers
        for server in config["mcpServers"].values()
        if "command" in server
    )


def test_product_workspace_survives_removed_cache(tmp_path):
    source = review_package(tmp_path)
    shutil.copyfile(
        ROOT / "plugins/vera/scripts/run_service_mcp.cjs",
        source / "scripts/run_service_mcp.cjs",
    )
    target = source / "mcp/workspace.cjs"
    target.parent.mkdir()
    target.write_text(
        (source / "modules/open-item-reconciliation/mcp/server.cjs")
        .read_text()
        .replace("../../../.codex-plugin", "../.codex-plugin")
    )
    write_index(source)
    process = subprocess.Popen(
        ["node", str(source / "scripts/run_service_mcp.cjs"), "mcp/workspace.cjs"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "MPARANZA_RUNTIME_ROOT": str(tmp_path / "runtime"),
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        },
    )
    try:
        before = call(process)
        shutil.rmtree(source)
        assert call(process) == before
    finally:
        stop(process)


def test_crashed_review_returns_error_without_replaying_request(tmp_path):
    source = review_package(tmp_path)
    server = source / "modules/open-item-reconciliation/mcp/server.cjs"
    server.write_text(
        server.read_text().replace(
            "const metadata=",
            'if(message.method==="crash")process.exit(7); const metadata=',
        )
    )
    write_index(source)
    process = launch_review(source, tmp_path)
    try:
        assert call(process)["version"] == "1"
        process.stdin.write('{"jsonrpc":"2.0","id":2,"method":"crash"}\n')
        process.stdin.flush()
        reply = json.loads(process.stdout.readline())
        assert reply["id"] == 2
        assert "Work may already be saved" in reply["error"]["message"]
    finally:
        stop(process)
