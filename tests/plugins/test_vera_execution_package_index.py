from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("product", ["vera", "clara", "lucia"])
@pytest.mark.parametrize("host", ["codex", "chatgpt-upload", "claude"])
def test_release_index_matches_every_final_host_projected_byte(host, product):
    filename = "vera-plugin.zip" if host == "codex" else f"vera-{host}-plugin.zip"
    if host == "chatgpt-upload":
        filename = "vera-chatgpt-upload.zip"
    filename = filename.replace("vera", product)
    with ZipFile(ROOT / "plugin_packages" / product / filename) as archive:
        indexes = [
            name for name in archive.namelist() if name.endswith("execution-files.json")
        ]
        assert len(indexes) == 1
        index = indexes[0]
        prefix = index.removesuffix("execution-files.json")
        manifest = json.loads(archive.read(index))
        expected = {
            name.removeprefix(prefix): hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith(prefix) and name != index and not name.endswith("/")
        }

    assert manifest["schema_version"] == 1
    assert manifest["files"] == expected
    assert "scripts/verified_execution.py" in expected
    router = f"mparanza-{product}" if host == "claude" else product
    assert f"skills/{router}/references/incident-recovery.md" in expected
    assert "scripts/reporting_product.py" in expected
    assert "scripts/model_data_report.py" in expected
    assert "scripts/workflow_usage.py" in expected
    assert "scripts/incident_tool_schemas.json" in expected
    assert "usage/pipelines.json" in expected
    with ZipFile(ROOT / "plugin_packages" / product / filename) as archive:
        connector = json.loads(archive.read(prefix + ".mcp.json"))["mcpServers"]
        assert f"{product}Incidents" not in connector
        assert connector[f"{product}IncidentHost"]["command"] == "node"
        assert all(
            "url" not in server and "serverUrl" not in server
            for server in connector.values()
        )
        if product != "vera":
            root_contract = archive.read(prefix + f"skills/{router}/SKILL.md").decode()
            assert "MPARANZA_REPORTING_BEGIN" in root_contract
            assert "actual signed receipt" in root_contract
            assert "HTTPS browser recovery page" in root_contract
            recovery_reference = archive.read(
                prefix + f"skills/{router}/references/incident-recovery.md"
            ).decode()
            assert (
                f"https://mparanza.com/{product}/incident-recovery"
                in recovery_reference
            )


@pytest.mark.parametrize("host", ["codex", "chatgpt-upload", "claude"])
def test_packaged_preflight_recovers_host_cache_hardlinks_without_manual_repair(
    tmp_path, host
):
    filenames = {
        "codex": "vera-plugin.zip",
        "chatgpt-upload": "vera-chatgpt-upload.zip",
        "claude": "vera-claude-plugin.zip",
    }
    installed = tmp_path / "installed"
    aliases = tmp_path / "host-cache"
    aliases.mkdir()
    with ZipFile(ROOT / "plugin_packages/vera" / filenames[host]) as archive:
        index = next(
            name for name in archive.namelist() if name.endswith("execution-files.json")
        )
        prefix = index.removesuffix("execution-files.json")
        # These are release-test archives generated from inspected repo source.
        for name in archive.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = Path(name.removeprefix(prefix))
            assert not relative.is_absolute() and ".." not in relative.parts
            path = installed / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
            alias = aliases / relative
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.hardlink_to(path)

    temporary = tmp_path / "os-temp"
    temporary.mkdir()
    environment = {
        **os.environ,
        "TMPDIR": str(temporary),
        "TMP": str(temporary),
        "TEMP": str(temporary),
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(installed / "scripts/verified_execution.py"),
            "--module",
            "journal-bank-reconciliation",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    # Preflight validates and releases its copy. Commands own a fresh copy
    # only while they execute; no returned path outlives the owning process.
    assert Path(json.loads(completed.stdout)["execution_root"]) == installed
    assert not list(temporary.glob("vera-verified-*"))
    relative = "modules/journal-bank-reconciliation/scripts/inspect_inputs.py"
    assert (installed / relative).stat().st_nlink == 2
    original = (aliases / relative).read_bytes()
    program = "\n".join(
        [
            "import json,runpy,subprocess,sys",
            "from pathlib import Path",
            "v=runpy.run_path(sys.argv[1])",
            "installed=Path(sys.argv[2])",
            "prepared=v['prepare_execution_root'](installed,'journal-bank-reconciliation')",
            "relative='modules/journal-bank-reconciliation/scripts/inspect_inputs.py'",
            "assert prepared!=installed",
            "assert (prepared/relative).stat().st_nlink==1",
            "assert (prepared/relative).read_bytes()==(installed/relative).read_bytes()",
            "r=subprocess.run([sys.executable,'-B',str(prepared/'modules/journal-bank-reconciliation/scripts/check_dependencies.py'),'--help'],capture_output=True,text=True)",
            "assert r.returncode==0,r.stderr",
            "print(json.dumps({'owned_root':str(prepared)}))",
        ]
    )
    helper = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            program,
            str(installed / "scripts/verified_execution.py"),
            str(installed),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )

    assert helper.returncode == 0, helper.stderr
    assert not Path(json.loads(helper.stdout)["owned_root"]).exists()
    assert not list(temporary.glob("vera-verified-*"))
    assert (installed / relative).stat().st_nlink == 2
    assert (aliases / relative).read_bytes() == original
    assert (installed / relative).read_bytes() == original
