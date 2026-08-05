from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "bilancio-xbrl-it" / "scripts"


def _load_runner():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / "run_xbrl_conformance.py"
    spec = importlib.util.spec_from_file_location("bilancio_conformance", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def _suite(path: Path) -> str:
    with ZipFile(path, "w") as archive:
        archive.writestr("XBRL-CONF-TEST/xbrl.xml", "<testcases/>")
    return runner._sha256(path)


def test_conformance_runner_requires_checksum_locked_suite(tmp_path: Path) -> None:
    package = tmp_path / "suite.zip"
    _suite(package)

    with pytest.raises(ValueError, match="checksum does not match"):
        runner.run_conformance(package, "0" * 64, tmp_path / "output")


def test_conformance_runner_enables_xbrl21_calculations_and_records_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "XBRL-CONF-TEST.zip"
    checksum = _suite(package)
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        report = Path(command[command.index("--testReport") + 1])
        report.write_text(
            "Index,Testcase,Id,Name,ReadMeFirst,Status,Expected,Actual\n"
            "xbrl.xml,test.xml,V-1,Valid,test.xbrl,pass,valid,\n",
            encoding="utf-8",
        )
        log = Path(command[command.index("--logFile") + 1])
        log.write_text("conformance run\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_conformance(package, checksum, tmp_path / "output")

    assert result["status"] == "PASS"
    assert result["variation_count"] == 1
    assert result["passed_count"] == 1
    assert result["failed_count"] == 0
    assert captured[captured.index("--calc") + 1] == "xbrl21"
    assert captured[captured.index("--internetConnectivity") + 1] == "offline"
    manifest = json.loads(
        (tmp_path / "output/conformance-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "PASS"
    assert not (tmp_path / "output/suite").exists()


def test_conformance_runner_retains_suite_when_variation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "XBRL-CONF-TEST.zip"
    checksum = _suite(package)

    def fake_run(command, **_kwargs):
        Path(command[command.index("--testReport") + 1]).write_text(
            "Index,Testcase,Id,Name,ReadMeFirst,Status,Expected,Actual\n"
            "xbrl.xml,test.xml,V-1,Invalid,test.xbrl,fail,invalid,\n",
            encoding="utf-8",
        )
        Path(command[command.index("--logFile") + 1]).write_text(
            "failed\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_conformance(package, checksum, tmp_path / "output")

    assert result["status"] == "FAIL"
    assert result["failed_count"] == 1
    assert result["failures"][0]["Id"] == "V-1"
    assert (tmp_path / "output/suite").is_dir()
